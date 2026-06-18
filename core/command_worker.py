"""
Command worker thread for Jarvis OS.

Drains CommandQueue and executes each command in its own try/except block,
keeping the audio-capture thread completely non-blocking even during 20-second
Gemini API calls or multi-sentence TTS responses.

Threading model
---------------

  ┌──────────────────────┐   put()   ┌───────────────────┐
  │  Audio loop (main)   │ ────────► │                   │
  ├──────────────────────┤           │   CommandQueue    │
  │  Console thread      │ ────────► │   (FIFO, capped)  │
  ├──────────────────────┤           │                   │
  │  Gesture thread      │ ────────► └─────────┬─────────┘
  └──────────────────────┘                     │ get()
                                               ▼
                                   ┌───────────────────────┐
                                   │   CommandWorker       │
                                   │   (single daemon thr) │
                                   │                       │
                                   │  on_command_start()   │  ← sets ENGINE.busy,
                                   │  handler(text)        │     UI → "thinking"
                                   │  on_command_end()     │  ← clears ENGINE.busy,
                                   └───────────────────────┘     UI → "idle"

One worker is the right choice for a single-user voice assistant — commands must
be serialised anyway (TTS occupies the speaker; mic is gated by ENGINE.busy).

Error isolation
---------------
Every handler() call is wrapped in try/except.  A crashing command handler
never kills the worker or the audio loop.  on_error() receives the item and
exception for optional recovery (e.g. speak an error message).  Exceptions
raised inside the callbacks are also swallowed so a bad callback can't cascade.

Graceful shutdown
-----------------
1. Caller signals:  COMMAND_QUEUE.shutdown()
2. Caller waits:    worker.stop(timeout=8.0)

The worker finishes the in-flight command, drains remaining items, then exits.
Set drain_on_shutdown=False for a hard stop that abandons queued items.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from core.command_queue import CommandQueue, CommandItem, COMMAND_QUEUE
from backend.utils.logger import LoggerManager

log = LoggerManager(name="jarvis.command_worker").get_logger()


class CommandWorker:
    """Single dedicated daemon thread that executes commands from CommandQueue."""

    def __init__(
        self,
        *,
        command_queue: Optional[CommandQueue] = None,
        handler: Callable[[str], None],
        name: str = "CommandWorker",
        on_command_start: Optional[Callable[[CommandItem], None]] = None,
        on_command_end:   Optional[Callable[[CommandItem], None]] = None,
        on_error:         Optional[Callable[[CommandItem, Exception], None]] = None,
        drain_on_shutdown: bool = True,
    ) -> None:
        """
        Parameters
        ----------
        command_queue
            Queue to drain.  Defaults to the module-level COMMAND_QUEUE singleton.
        handler
            Executes a command string — wire to commands.handle_command.
        name
            Thread name shown in debuggers and log lines.
        on_command_start
            Called on the worker thread just *before* handler().
            Use this to set ENGINE.busy = True and flip UI to "thinking".
        on_command_end
            Called on the worker thread just *after* handler(), whether it
            succeeded or raised.  Use this to clear ENGINE.busy and flip UI
            to "idle".  Also set ENGINE.flush_pending = True here so the
            audio loop can flush the mic buffer after TTS without a stream
            race.
        on_error
            Called when handler() raises, before on_command_end.  Receives
            the CommandItem and the exception.  Speak an error message here
            if you want the user to hear that something went wrong.
        drain_on_shutdown
            True (default): finish all queued items before exiting.
            False: exit as soon as shutdown is signalled.
        """
        self._queue  = command_queue or COMMAND_QUEUE
        self._handler = handler
        self._name    = name
        self._on_start  = on_command_start
        self._on_end    = on_command_end
        self._on_error  = on_error
        self._drain     = drain_on_shutdown

        self._thread: Optional[threading.Thread] = None
        self._active_item: Optional[CommandItem] = None
        self._active_lock = threading.Lock()

        self._ok_count  = 0
        self._err_count = 0

    # ── lifecycle ─────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the worker thread.  Safe to call multiple times (idempotent)."""
        if self._thread and self._thread.is_alive():
            log.warning("%s is already running", self._name)
            return
        self._thread = threading.Thread(
            target=self._run,
            name=self._name,
            daemon=True,
        )
        self._thread.start()
        log.info("%s started (tid=%s)", self._name, self._thread.ident)

    def stop(self, timeout: float = 8.0) -> None:
        """
        Join the worker thread, waiting up to *timeout* seconds.

        You must call CommandQueue.shutdown() first so the worker exits its
        loop — this method only blocks until it finishes.
        """
        if self._thread and self._thread.is_alive():
            log.info("%s waiting to finish (timeout=%.1fs)…", self._name, timeout)
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                log.warning("%s did not stop within %.1fs", self._name, timeout)
            else:
                log.info("%s stopped cleanly", self._name)

    # ── internal work loop ────────────────────────────────────────────────

    def _run(self) -> None:
        log.info("%s entering work loop", self._name)
        try:
            while True:
                # Exit when shutdown was requested AND (draining disabled OR
                # queue is already empty).
                if self._queue.is_shutting_down:
                    if not self._drain or self._queue.depth == 0:
                        break

                item = self._queue.get(timeout=1.0)
                if item is None:
                    continue  # timed out — re-check shutdown flag and loop

                self._execute(item)
                self._queue.task_done()

        except Exception:
            log.exception("%s crashed unexpectedly", self._name)
        finally:
            log.info(
                "%s exited  ok=%d  errors=%d",
                self._name, self._ok_count, self._err_count,
            )

    def _execute(self, item: CommandItem) -> None:
        """Run one command with lifecycle hooks and full error isolation."""
        with self._active_lock:
            self._active_item = item

        log.info("[%s] executing: %r", item.source.value, item.text)

        # ── pre-execution hook (set busy flag, UI state) ──────────────────
        if self._on_start:
            try:
                self._on_start(item)
            except Exception:
                log.exception("%s on_command_start raised", self._name)

        # ── execute ───────────────────────────────────────────────────────
        try:
            self._handler(item.text)
            self._ok_count += 1
            log.debug("[%s] done: %r", item.source.value, item.text)
        except Exception as exc:
            self._err_count += 1
            log.exception(
                "[%s] error handling %r: %s", item.source.value, item.text, exc
            )
            if self._on_error:
                try:
                    self._on_error(item, exc)
                except Exception:
                    log.exception("%s on_error callback raised", self._name)

        # ── post-execution hook (clear busy flag, flush mic, UI state) ────
        finally:
            if self._on_end:
                try:
                    self._on_end(item)
                except Exception:
                    log.exception("%s on_command_end callback raised", self._name)
            with self._active_lock:
                self._active_item = None

    # ── introspection ─────────────────────────────────────────────────────

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def current_command(self) -> Optional[str]:
        """Text of the command currently being executed, or None if idle."""
        with self._active_lock:
            item = self._active_item
        return item.text if item else None

    @property
    def stats(self) -> dict:
        return {
            "ok":     self._ok_count,
            "errors": self._err_count,
            "active": self.current_command,
            "alive":  self.is_alive,
        }
