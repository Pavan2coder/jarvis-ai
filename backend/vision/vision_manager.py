"""
VisionManager: single-owner camera hub with subscriber frame broadcasting.

One camera. Many consumers. Thread-safe.

Architecture
────────────
  FrameProvider (hardware)
         │
         ▼
  VisionManager._capture_loop          ← single daemon thread owns the device
         │
         │  _preprocess(frame, cfg)    ← per-subscriber transforms applied here
         │    flip_horizontal           (gesture = True;  OCR/face = False)
         │    resize                    (optional downsample)
         │    grayscale                 (optional for OCR)
         │
    ┌────┼────┬──────────────┐
    ▼    ▼    ▼              ▼
  sub0  sub1  sub2  …     get_latest_frame()  ← pull-style for camera_ops etc.
  Q+T   Q+T   Q+T            (copy under lock, no dedicated thread)

Each subscriber gets its own queue (maxsize configurable, default 2) and worker
thread.  Slow subscribers drop frames; they never stall the capture loop.

Integration
───────────
Register before or after start — subscribers added before start() are started
by start(); subscribers added while running are started immediately.

    from backend.vision.vision_manager import subscribe, start_vision, SubscriberConfig

    def my_on_frame(frame: np.ndarray) -> None:
        ...

    subscribe("my_module", my_on_frame, SubscriberConfig(fps_limit=15))
    start_vision()          # or called once at program boot

    # later:
    unsubscribe("my_module")
    stop_vision()           # joins all subscriber threads, then releases camera

Shutdown ordering
─────────────────
stop() always:
    1. signals capture loop to exit
    2. stops + joins all subscriber handles
    3. joins the capture thread
    4. closes the provider (releases VideoCapture)

This guarantees no subscriber thread reads from a closed device.

See bottom of file for migration examples: gesture engine, face recognition, OCR.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from backend.vision.frame_provider import CameraConfig, FrameProvider

log = logging.getLogger("JARVIS.vision.manager")


# ──────────────────────────────────────────────────────────────────────────────
# Subscriber configuration
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SubscriberConfig:
    """
    Per-subscriber tuning.

    fps_limit:         Max frames per second delivered to this subscriber.
                       None = every captured frame.
    queue_maxsize:     Drop frames rather than block if the subscriber falls
                       behind.  2 is usually right; raise for bursty workloads.
    flip_horizontal:   Mirror the frame.  True for gesture (selfie-view);
                       False for OCR and face recognition (mirroring breaks text
                       and lateralises face descriptors).
    resize:            (width, height) to apply after flip, before delivery.
    grayscale:         Convert to single-channel BGR→GRAY (useful for OCR).
    """
    fps_limit: Optional[float] = None
    queue_maxsize: int = 2
    flip_horizontal: bool = False
    resize: Optional[Tuple[int, int]] = None
    grayscale: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# Internal subscriber handle
# ──────────────────────────────────────────────────────────────────────────────

class _SubscriberHandle:
    """Manages one subscriber's queue, worker thread, and fps gate."""

    def __init__(
        self,
        name: str,
        callback: Callable[[np.ndarray], None],
        config: SubscriberConfig,
    ) -> None:
        self.name = name
        self.callback = callback
        self.config = config

        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=config.queue_maxsize)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_frame_ts: float = 0.0
        self._min_interval: float = (1.0 / config.fps_limit) if config.fps_limit else 0.0

    # ---- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"vision-sub-{self.name}",
            daemon=True,
        )
        self._thread.start()
        log.debug("Subscriber %r worker started", self.name)

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        log.debug("Subscriber %r worker stopped", self.name)

    # ---- frame delivery ------------------------------------------------------

    def put_frame(self, frame: np.ndarray) -> None:
        """Non-blocking. Silently drops if subscriber queue is full or fps-gated."""
        now = time.monotonic()
        if self._min_interval and (now - self._last_frame_ts) < self._min_interval:
            return
        self._last_frame_ts = now
        try:
            self._queue.put_nowait(frame)
        except queue.Full:
            pass  # subscriber is overloaded; drop this frame

    # ---- worker loop ---------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                frame = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.callback(frame)
            except Exception:
                log.exception("Subscriber %r callback raised", self.name)


# ──────────────────────────────────────────────────────────────────────────────
# VisionManager
# ──────────────────────────────────────────────────────────────────────────────

class VisionManager:
    """
    Single owner of the camera.  Subscribers receive preprocessed frame copies
    through per-subscriber queues + worker threads.

    Use the module-level helpers (start_vision / stop_vision / subscribe /
    unsubscribe / get_latest_frame) rather than instantiating this directly.
    """

    def __init__(self) -> None:
        self._provider: Optional[FrameProvider] = None
        self._capture_thread: Optional[threading.Thread] = None
        self._running = False

        # Pull-style access (camera_ops, snapshots, etc.)
        self._frame_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None

        # Subscriber registry
        self._subs_lock = threading.RLock()
        self._subscribers: Dict[str, _SubscriberHandle] = {}

    # ---- lifecycle -----------------------------------------------------------

    def start(self, config: Optional[CameraConfig] = None) -> bool:
        """Open the camera and start broadcasting frames. Idempotent."""
        if self._running:
            log.warning("VisionManager.start() called while already running — ignored")
            return True

        self._provider = FrameProvider(config)
        if not self._provider.open():
            self._provider = None
            return False

        self._running = True
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            name="vision-capture",
            daemon=True,
        )
        self._capture_thread.start()

        # Start any subscribers that were registered before start()
        with self._subs_lock:
            for handle in self._subscribers.values():
                handle.start()

        log.info(
            "VisionManager started — source=%r  resolution=%s",
            self._provider.source,
            self._provider.resolution,
        )
        return True

    def stop(self) -> None:
        """
        Graceful shutdown.  Order guaranteed:
          1. capture loop exits
          2. subscriber threads joined
          3. capture thread joined
          4. provider closed
        """
        if not self._running:
            return

        self._running = False

        # 1. Stop subscriber threads (they stop reading from queues)
        with self._subs_lock:
            handles = list(self._subscribers.values())
        for handle in handles:
            handle.stop()

        # 2. Join capture thread
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=3.0)
            self._capture_thread = None

        # 3. Close camera — only after capture thread is gone
        if self._provider is not None:
            self._provider.close()
            self._provider = None

        with self._frame_lock:
            self._latest_frame = None

        log.info("VisionManager stopped")

    # ---- subscriber management -----------------------------------------------

    def subscribe(
        self,
        name: str,
        callback: Callable[[np.ndarray], None],
        config: Optional[SubscriberConfig] = None,
    ) -> bool:
        """
        Register a frame subscriber.  Safe to call before or after start().

        Returns True.  If a subscriber with the same name already exists it is
        replaced (old worker stopped first).
        """
        cfg = config or SubscriberConfig()
        handle = _SubscriberHandle(name, callback, cfg)

        with self._subs_lock:
            if name in self._subscribers:
                log.warning("Subscriber %r already registered — replacing", name)
                self._subscribers[name].stop()
            self._subscribers[name] = handle
            already_running = self._running

        if already_running:
            handle.start()

        log.info(
            "Subscriber %r registered — fps_limit=%s  flip=%s  resize=%s  gray=%s",
            name, cfg.fps_limit, cfg.flip_horizontal, cfg.resize, cfg.grayscale,
        )
        return True

    def unsubscribe(self, name: str) -> bool:
        """Deregister a subscriber and stop its worker thread."""
        with self._subs_lock:
            handle = self._subscribers.pop(name, None)
        if handle is None:
            log.warning("unsubscribe(%r) — not found", name)
            return False
        handle.stop()
        log.info("Subscriber %r unregistered", name)
        return True

    def subscriber_names(self) -> List[str]:
        with self._subs_lock:
            return list(self._subscribers.keys())

    # ---- pull-style access ---------------------------------------------------

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """
        Return a copy of the most recent raw (unflipped, unprocessed) frame.
        Returns None if the manager is not running or no frame has been captured yet.
        Thread-safe.  Used by camera_ops and other non-subscriber consumers.
        """
        with self._frame_lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    # ---- status --------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    # ---- internals -----------------------------------------------------------

    def _capture_loop(self) -> None:
        log.info("Vision capture loop started")
        consecutive_failures = 0

        while self._running:
            frame = self._provider.read() if self._provider else None

            if frame is None:
                consecutive_failures += 1
                if consecutive_failures >= 30:
                    log.error(
                        "Camera read failed 30 consecutive times — stopping VisionManager"
                    )
                    self._running = False
                    break
                time.sleep(0.01)
                continue

            consecutive_failures = 0

            # Update pull-style latest frame (raw, no copy needed — only this
            # thread writes _latest_frame; readers copy under lock)
            with self._frame_lock:
                self._latest_frame = frame

            # Broadcast preprocessed copies to all subscribers
            with self._subs_lock:
                handles = list(self._subscribers.values())

            for handle in handles:
                processed = self._preprocess(frame, handle.config)
                handle.put_frame(processed)

        log.info("Vision capture loop ended")

    def _preprocess(self, frame: np.ndarray, cfg: SubscriberConfig) -> np.ndarray:
        """
        Apply per-subscriber transforms.  Always returns a new array.

        Flip is applied first so that resize/grayscale operate on the
        correctly-oriented image.  OCR and face recognition must NOT flip
        (mirroring reverses text and lateralises face descriptors).
        """
        # cv2.flip returns a new ndarray; frame.copy() is used when no flip is needed
        out = cv2.flip(frame, 1) if cfg.flip_horizontal else frame.copy()
        if cfg.resize is not None:
            out = cv2.resize(out, cfg.resize)
        if cfg.grayscale:
            out = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
        return out


# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton  (mirrors audio_engine.ENGINE / gesture_engine.ENGINE)
# ──────────────────────────────────────────────────────────────────────────────

MANAGER: Optional[VisionManager] = None


def start_vision(config: Optional[CameraConfig] = None) -> bool:
    """Initialize and start the shared VisionManager. Idempotent."""
    global MANAGER
    if MANAGER is None:
        MANAGER = VisionManager()
    return MANAGER.start(config)


def stop_vision() -> None:
    """Gracefully stop the VisionManager and release the camera."""
    global MANAGER
    if MANAGER is not None:
        MANAGER.stop()


def subscribe(
    name: str,
    callback: Callable[[np.ndarray], None],
    config: Optional[SubscriberConfig] = None,
) -> bool:
    """Register a frame subscriber on the shared manager.  Safe before start_vision()."""
    global MANAGER
    if MANAGER is None:
        MANAGER = VisionManager()
    return MANAGER.subscribe(name, callback, config)


def unsubscribe(name: str) -> bool:
    """Deregister a frame subscriber."""
    if MANAGER is None:
        return False
    return MANAGER.unsubscribe(name)


def get_latest_frame() -> Optional[np.ndarray]:
    """Pull-style access to the most recent raw frame.  Returns None if not running."""
    if MANAGER is None:
        return None
    return MANAGER.get_latest_frame()


# ──────────────────────────────────────────────────────────────────────────────
# INTEGRATION EXAMPLES
# ──────────────────────────────────────────────────────────────────────────────
#
# ── 1. Gesture Engine migration ────────────────────────────────────────────────
#
# Before (gesture_engine.py owns the camera):
#
#   class GestureEngine:
#       def _run_loop(self):
#           self.cap = cv2.VideoCapture(camera_idx)      # ← DELETE
#           while self.running:
#               ret, frame = self.cap.read()             # ← DELETE
#               frame = cv2.flip(frame, 1)               # ← DELETE
#               with self._frame_lock:                   # ← DELETE
#                   self._latest_frame = frame.copy()   # ← DELETE
#               ... process landmarks ...
#           self.cap.release()                           # ← DELETE
#
# After (gesture engine becomes a VisionManager subscriber):
#
#   from backend.vision.vision_manager import subscribe, unsubscribe, SubscriberConfig
#
#   class GestureEngine:
#       def start(self) -> bool:
#           ...
#           # Subscribe — flip_horizontal mirrors the view for selfie gestures.
#           # VisionManager must already be started (or start it here).
#           subscribe(
#               "gesture",
#               self._process_frame,
#               SubscriberConfig(fps_limit=30, flip_horizontal=True),
#           )
#           self.running = True
#           return True
#
#       def stop(self):
#           unsubscribe("gesture")
#           self.running = False
#           ...
#
#       def _process_frame(self, frame: np.ndarray) -> None:
#           """Called by VisionManager's subscriber worker thread."""
#           # frame is already flipped; cache it for camera_ops / get_latest_frame()
#           with self._frame_lock:
#               self._latest_frame = frame.copy()
#           gesture_state_manager.increment_frame_count()
#           # ... all existing landmark tracking + action dispatch unchanged ...
#
#   NOTE: Until gesture_engine.py is migrated, do NOT run VisionManager AND the
#   old GestureEngine simultaneously — they will both open the same camera and
#   cause a device conflict.  Migration is required before running both.
#
#
# ── 2. Face Recognition ────────────────────────────────────────────────────────
#
#   from backend.vision.vision_manager import subscribe, SubscriberConfig
#
#   class FaceRecognizer:
#       def start(self):
#           subscribe(
#               "face_recognition",
#               self._on_frame,
#               SubscriberConfig(
#                   fps_limit=15,
#                   flip_horizontal=False,  # DO NOT flip — face descriptors are lateral
#                   resize=(320, 240),      # downsample to speed up detection
#               ),
#           )
#
#       def _on_frame(self, frame: np.ndarray) -> None:
#           # frame: 320×240, BGR, NOT mirrored
#           faces = self._detector.detect(frame)
#           ...
#
#
# ── 3. OCR ─────────────────────────────────────────────────────────────────────
#
#   from backend.vision.vision_manager import subscribe, SubscriberConfig
#
#   class OCREngine:
#       def start(self):
#           subscribe(
#               "ocr",
#               self._on_frame,
#               SubscriberConfig(
#                   fps_limit=5,            # OCR is slow; 5 fps is plenty
#                   flip_horizontal=False,  # MUST NOT flip — mirroring reverses text
#                   grayscale=True,         # single-channel improves Tesseract accuracy
#               ),
#           )
#
#       def _on_frame(self, frame: np.ndarray) -> None:
#           # frame: grayscale, NOT mirrored
#           text = pytesseract.image_to_string(frame)
#           ...
#
#
# ── 4. camera_ops migration (pull-style, no subscriber needed) ─────────────────
#
#   Before:
#       engine = gesture_engine.ENGINE
#       frame = engine.get_latest_frame()   # borrows from gesture engine
#
#   After:
#       from backend.vision.vision_manager import get_latest_frame
#       frame = get_latest_frame()          # pulls raw frame from VisionManager
#                                           # (VisionManager's _latest_frame is
#                                           #  raw/unflipped — add flip if needed
#                                           #  for the specific use-case)
#
#
# ── 5. Wiring in backend/main.py ──────────────────────────────────────────────
#
#   from backend.vision.vision_manager import start_vision, stop_vision
#   from backend.core import config
#
#   # Boot — before starting gesture/face/OCR subscribers
#   cam_cfg = CameraConfig(source=getattr(config, "CAMERA_INDEX", 0))
#   if not start_vision(cam_cfg):
#       logger.error("VisionManager failed to open camera — vision features disabled")
#
#   # Shutdown — register before audio engine (camera is lower priority)
#   shutdown_manager.register_handler("vision_manager", stop_vision, priority=25)
