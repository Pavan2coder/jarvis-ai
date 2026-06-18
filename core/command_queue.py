"""
Thread-safe FIFO command queue for Jarvis OS.

Decouples command producers (voice, console, gesture) from the executor so the
audio-capture thread is never stalled by Gemini API calls or TTS playback.

Threading model
---------------
Producers (audio loop, console thread, gesture engine) call put() — fire and
forget, never blocks.  The single CommandWorker thread calls get() in a tight
loop.  Queue depth is capped at maxsize; excess items are dropped with a
warning so a slow worker can never create unbounded latency.

Shutdown
--------
Call shutdown() to signal the queue is closing.  Workers detect
is_shutting_down and exit their loop once the queue is drained (or immediately
if drain_on_shutdown=False).  All subsequent put() calls are dropped.
"""

from __future__ import annotations

import queue
import threading
import time
import logging
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Optional

from backend.utils.logger import LoggerManager

log = LoggerManager(name="jarvis.command_queue").get_logger()


# ─────────────────────────────────────────────
#  Public types
# ─────────────────────────────────────────────

class CommandSource(str, Enum):
    """Origin of a queued command."""
    VOICE   = "voice"
    CONSOLE = "console"
    GESTURE = "gesture"
    SYSTEM  = "system"   # programmatic / internal


class CommandPriority(IntEnum):
    """
    Reserved for future routing logic — the queue is plain FIFO today.
    Store priority on each item so callers can tag urgency without a
    breaking API change when the queue gains priority support.
    """
    HIGH   = 0
    NORMAL = 1
    LOW    = 2


@dataclass
class CommandItem:
    """A single queued command."""
    text:      str
    source:    CommandSource
    timestamp: float         = field(default_factory=time.monotonic)
    priority:  CommandPriority = CommandPriority.NORMAL
    metadata:  dict          = field(default_factory=dict)


# ─────────────────────────────────────────────
#  Queue
# ─────────────────────────────────────────────

class CommandQueue:
    """
    Thread-safe FIFO command queue with non-blocking put() and graceful-
    shutdown support.

    Designed for one-producer-many or many-producers-one-consumer scenarios.
    The internal stdlib queue handles all locking; the extra _stats_lock only
    guards the counters so the hot put()/get() paths stay uncontested.
    """

    def __init__(self, maxsize: int = 8) -> None:
        self._q: queue.Queue[CommandItem] = queue.Queue(maxsize=maxsize)
        self._shutdown = threading.Event()
        self._stats_lock = threading.Lock()
        self._put_count  = 0
        self._get_count  = 0
        self._drop_count = 0

    # ── producer ──────────────────────────────────────────────

    def put(
        self,
        text: str,
        source: CommandSource,
        priority: CommandPriority = CommandPriority.NORMAL,
        metadata: Optional[dict] = None,
    ) -> bool:
        """
        Enqueue a command.  Never blocks.

        Returns True on success, False if the queue is full or already
        shutting down.  On failure a warning is logged so developers can tune
        maxsize without having to add instrumentation.
        """
        if self._shutdown.is_set():
            log.warning("Queue shutting down — dropped [%s] %r", source.value, text)
            return False

        item = CommandItem(
            text=text.strip(),
            source=source,
            priority=priority,
            metadata=metadata or {},
        )
        try:
            self._q.put_nowait(item)
            with self._stats_lock:
                self._put_count += 1
            log.debug("Enqueued [%s] %r  depth=%d", source.value, text, self._q.qsize())
            return True
        except queue.Full:
            with self._stats_lock:
                self._drop_count += 1
            log.warning(
                "Queue full (cap=%d) — dropped [%s] %r",
                self._q.maxsize, source.value, text,
            )
            return False

    # ── consumer ──────────────────────────────────────────────

    def get(self, timeout: float = 1.0) -> Optional[CommandItem]:
        """
        Dequeue the next item, waiting up to *timeout* seconds.

        Returns None on timeout.  Workers should loop and re-check
        is_shutting_down after each None return.
        """
        try:
            item = self._q.get(timeout=timeout)
            with self._stats_lock:
                self._get_count += 1
            return item
        except queue.Empty:
            return None

    def task_done(self) -> None:
        """Notify the queue that a previously dequeued item has been processed."""
        self._q.task_done()

    # ── lifecycle ─────────────────────────────────────────────

    def shutdown(self) -> None:
        """
        Signal all workers to stop.

        Workers will finish any in-progress command, drain remaining queued
        items (if drain_on_shutdown=True), then exit.  All subsequent put()
        calls are rejected.
        """
        log.info("CommandQueue shutdown (pending=%d)", self.depth)
        self._shutdown.set()

    # ── introspection ─────────────────────────────────────────

    @property
    def is_shutting_down(self) -> bool:
        return self._shutdown.is_set()

    @property
    def depth(self) -> int:
        return self._q.qsize()

    @property
    def stats(self) -> dict:
        with self._stats_lock:
            return {
                "enqueued":      self._put_count,
                "processed":     self._get_count,
                "dropped":       self._drop_count,
                "pending":       self._q.qsize(),
                "shutting_down": self._shutdown.is_set(),
            }


# ─────────────────────────────────────────────
#  Module-level singleton
# ─────────────────────────────────────────────

# All producers and the worker import this.  A fresh queue is created once at
# import time; the singleton is replaced only in unit tests that need isolation.
COMMAND_QUEUE: CommandQueue = CommandQueue(maxsize=8)
