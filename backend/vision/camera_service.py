"""
CameraService — camera lifecycle, health monitoring, and automatic recovery.

Sits between cv2.VideoCapture (hardware) and VisionManager (pub/sub hub).
Drop-in replacement for FrameProvider: same read()/open()/close()/is_open()/
resolution interface, plus a watchdog thread that drives automatic recovery
and FPS telemetry.

Layer diagram
─────────────
  Subscribers (gesture, face, OCR)
        │
  VisionManager  (pub/sub, per-subscriber preprocessing)
        │
  CameraService  ← this file
        │
  cv2.VideoCapture  (hardware)

Single-owner contract
─────────────────────
  cv2.VideoCapture is opened by exactly one CameraService instance at a time.
  Never run this alongside a live FrameProvider or legacy GestureEngine on the
  same device index — the second handle will fail or return garbage frames.

Drop-in swap for VisionManager
──────────────────────────────
  # Before
  from backend.vision.frame_provider import CameraConfig, FrameProvider
  self._provider = FrameProvider(config)

  # After
  from backend.vision.camera_service import CameraConfig, ServiceConfig, CameraService
  self._provider = CameraService(config, ServiceConfig())

Recovery workflow
─────────────────
  RUNNING  ──(watchdog detects unhealthy)──►  RECOVERING
      ▲                                             │
      │            backoff = base * 2^attempt       │
      │              (capped at backoff_max)         ▼
      └─(cap opened OK)──────────────────  release → reopen
                                          attempt += 1 on failure
                                          → ERROR after max_attempts
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional, Tuple, Union

import cv2
import numpy as np

# Re-export CameraConfig so callers need only import from this module.
from backend.vision.frame_provider import CameraConfig

log = logging.getLogger("JARVIS.vision.camera_service")


# ──────────────────────────────────────────────────────────────────────────────
# State & configuration
# ──────────────────────────────────────────────────────────────────────────────

class CameraState(Enum):
    UNINITIALIZED = auto()
    INITIALIZING  = auto()
    RUNNING       = auto()
    RECOVERING    = auto()
    ERROR         = auto()
    RELEASED      = auto()


@dataclass
class ServiceConfig:
    """
    Recovery policy and health thresholds — separate from hardware settings.

    Defaults are conservative and safe for a 30 fps webcam.
    """
    # Recovery
    max_recovery_attempts: int   = 5
    recovery_backoff_base:  float = 1.0    # seconds; actual = base * 2^attempt
    recovery_backoff_max:   float = 30.0   # ceiling on backoff

    # Watchdog timing
    health_check_interval:  float = 2.0    # seconds between health probes

    # Thresholds — a single criterion failing triggers recovery
    failure_threshold:      int   = 10     # consecutive read() failures
    fps_drop_ratio:         float = 0.4    # actual < target * ratio → unhealthy
    success_rate_min:       float = 0.75   # rolling-window floor

    # Rolling-window size (frames) for FPS and success-rate calculations
    fps_window:             int   = 30


# ──────────────────────────────────────────────────────────────────────────────
# Health snapshot (immutable, safe to inspect from any thread)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class CameraHealth:
    state:                    CameraState
    fps_actual:               float
    fps_target:               float
    success_rate:             float        # fraction over rolling window
    consecutive_failures:     int
    total_recoveries:         int
    recovery_attempt_current: int          # resets to 0 on successful recovery
    last_error:               Optional[str]
    uptime_seconds:           float
    resolution:               Tuple[int, int]
    is_healthy:               bool


# ──────────────────────────────────────────────────────────────────────────────
# CameraService
# ──────────────────────────────────────────────────────────────────────────────

class CameraService:
    """
    Thread-safe camera lifecycle manager.

    Compatible with FrameProvider's read()/open()/close()/is_open()/resolution
    interface so it can be swapped in wherever FrameProvider is used today.

    VisionManager's capture thread is the only caller of read().
    The watchdog and recovery threads never call read() — they only inspect
    health counters and (during recovery) release/reopen the cap.

    Callbacks run on background threads — keep them short and non-blocking.
    """

    def __init__(
        self,
        camera_config: Optional[CameraConfig] = None,
        service_config: Optional[ServiceConfig] = None,
        *,
        on_state_change: Optional[Callable[[CameraState], None]] = None,
        on_recovery_success: Optional[Callable[[int], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._cam_cfg  = camera_config  or CameraConfig()
        self._svc_cfg  = service_config or ServiceConfig()

        self._cap: Optional[cv2.VideoCapture] = None
        self._state = CameraState.UNINITIALIZED
        self._start_time: float = 0.0

        # Lock hierarchy (always acquire in this order to avoid deadlock):
        #   _state_lock  →  _cap_lock  →  _stats_lock
        self._state_lock = threading.Lock()   # guards state + recovery counters
        self._cap_lock   = threading.RLock()  # guards _cap access
        self._stats_lock = threading.Lock()   # guards fps/success rolling windows

        # Health counters (protected by _stats_lock)
        self._fps_times:       deque[float] = deque()  # timestamps of successful reads
        self._success_window:  deque[bool]  = deque()  # True/False for last N reads
        self._consec_failures: int = 0                 # since last successful read

        # Recovery counters (protected by _state_lock)
        self._total_recoveries:   int = 0
        self._recovery_attempt:   int = 0
        self._last_error: Optional[str] = None

        # Watchdog
        self._shutdown = threading.Event()
        self._watchdog: Optional[threading.Thread] = None

        # Callbacks
        self._on_state_change    = on_state_change
        self._on_recovery_success = on_recovery_success
        self._on_error           = on_error

    # ──────────────────────────────────────────────────────────────────────────
    # Public lifecycle  (mirrors FrameProvider)
    # ──────────────────────────────────────────────────────────────────────────

    def open(self) -> bool:
        """
        Open the camera and start the health watchdog.  Idempotent.
        Returns True if the camera is ready for read().
        """
        with self._state_lock:
            if self._state in (CameraState.RUNNING, CameraState.INITIALIZING):
                log.debug("CameraService.open() called while already %s", self._state.name)
                return True
            self._set_state(CameraState.INITIALIZING)

        ok = self._open_cap()
        with self._state_lock:
            if ok:
                self._start_time = time.monotonic()
                self._recovery_attempt = 0
                self._set_state(CameraState.RUNNING)
                self._start_watchdog()
                log.info(
                    "CameraService ready — source=%r  %dx%d  target_fps=%d",
                    self._cam_cfg.source,
                    *self.resolution,
                    self._cam_cfg.target_fps,
                )
            else:
                self._set_state(CameraState.ERROR)
        return ok

    def close(self) -> None:
        """Stop the watchdog and release the camera. Idempotent."""
        self._shutdown.set()
        if self._watchdog and self._watchdog.is_alive():
            self._watchdog.join(timeout=5.0)
        self._watchdog = None

        with self._cap_lock:
            if self._cap is not None:
                self._cap.release()
                self._cap = None

        with self._state_lock:
            self._set_state(CameraState.RELEASED)

        log.info("CameraService released — source=%r", self._cam_cfg.source)

    # ──────────────────────────────────────────────────────────────────────────
    # Frame access  (mirrors FrameProvider)
    # ──────────────────────────────────────────────────────────────────────────

    def read(self) -> Optional[np.ndarray]:
        """
        Return one raw, unprocessed frame (BGR, unflipped) or None on failure.
        Must only be called from the owning capture thread (same constraint as
        FrameProvider).  Updates internal health counters.
        """
        with self._cap_lock:
            if self._cap is None or not self._cap.isOpened():
                self._record(False)
                return None
            ret, frame = self._cap.read()

        if ret:
            self._record(True)
            return frame
        self._record(False)
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Resolution management
    # ──────────────────────────────────────────────────────────────────────────

    def set_resolution(self, width: int, height: int) -> bool:
        """
        Apply a new resolution at runtime.  Returns True if the camera accepted it.
        Falls back to original config values if rejected.
        """
        with self._cap_lock:
            if self._cap is None or not self._cap.isOpened():
                return False
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        accepted = (actual_w == width) and (actual_h == height)
        if accepted:
            self._cam_cfg.width  = width
            self._cam_cfg.height = height
            log.info("CameraService: resolution set to %dx%d", width, height)
        else:
            log.warning(
                "CameraService: resolution %dx%d rejected — camera is using %dx%d",
                width, height, actual_w, actual_h,
            )
        return accepted

    @property
    def resolution(self) -> Tuple[int, int]:
        """Current (width, height) queried from the cap, or config values if closed."""
        with self._cap_lock:
            if self._cap is None or not self._cap.isOpened():
                return (self._cam_cfg.width, self._cam_cfg.height)
            return (
                int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Introspection  (mirrors FrameProvider)
    # ──────────────────────────────────────────────────────────────────────────

    def is_open(self) -> bool:
        with self._cap_lock:
            return self._cap is not None and self._cap.isOpened()

    @property
    def source(self) -> Union[int, str]:
        return self._cam_cfg.source

    # ──────────────────────────────────────────────────────────────────────────
    # FPS monitoring
    # ──────────────────────────────────────────────────────────────────────────

    def fps_actual(self) -> float:
        """
        Measured FPS over the rolling window.  Returns 0.0 until the window fills.
        Computed from the timestamps of successful read() calls only.
        """
        with self._stats_lock:
            times = list(self._fps_times)
        if len(times) < 2:
            return 0.0
        return (len(times) - 1) / (times[-1] - times[0])

    # ──────────────────────────────────────────────────────────────────────────
    # Health
    # ──────────────────────────────────────────────────────────────────────────

    def get_health(self) -> CameraHealth:
        """Thread-safe snapshot of current service health."""
        with self._state_lock:
            state              = self._state
            total_recoveries   = self._total_recoveries
            recovery_attempt   = self._recovery_attempt
            last_error         = self._last_error
            uptime = (
                round(time.monotonic() - self._start_time, 1)
                if self._start_time else 0.0
            )
        return CameraHealth(
            state                    = state,
            fps_actual               = round(self.fps_actual(), 2),
            fps_target               = float(self._cam_cfg.target_fps),
            success_rate             = round(self._success_rate(), 3),
            consecutive_failures     = self._consec_failures,
            total_recoveries         = total_recoveries,
            recovery_attempt_current = recovery_attempt,
            last_error               = last_error,
            uptime_seconds           = uptime,
            resolution               = self.resolution,
            is_healthy               = self._healthy(),
        )

    @property
    def state(self) -> CameraState:
        return self._state

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _open_cap(self) -> bool:
        """Open/reopen VideoCapture with warm-up.  Caller must hold no locks."""
        cfg = self._cam_cfg
        with self._cap_lock:
            if self._cap is not None:
                self._cap.release()
            cap = cv2.VideoCapture(cfg.source)
            if not cap.isOpened():
                with self._state_lock:
                    self._last_error = f"Cannot open camera source {cfg.source!r}"
                log.error("CameraService: %s", self._last_error)
                cap.release()
                return False

            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  cfg.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
            cap.set(cv2.CAP_PROP_FPS,          cfg.target_fps)

            for _ in range(5):     # flush buffered stale frames
                cap.read()

            self._cap = cap

        # Reset rolling windows after a successful (re)open
        with self._stats_lock:
            self._fps_times.clear()
            self._success_window.clear()
            self._consec_failures = 0
        return True

    def _record(self, success: bool) -> None:
        """Update rolling health windows.  Called from the capture thread."""
        now    = time.monotonic()
        window = self._svc_cfg.fps_window

        with self._stats_lock:
            if success:
                self._fps_times.append(now)
                if len(self._fps_times) > window:
                    self._fps_times.popleft()
                self._consec_failures = 0
            else:
                self._consec_failures += 1

            self._success_window.append(success)
            if len(self._success_window) > window:
                self._success_window.popleft()

    def _success_rate(self) -> float:
        with self._stats_lock:
            window = list(self._success_window)
        if not window:
            return 1.0
        return sum(window) / len(window)

    def _healthy(self) -> bool:
        if self._state != CameraState.RUNNING:
            return False
        svc = self._svc_cfg

        # Consecutive failure burst
        if self._consec_failures >= svc.failure_threshold:
            return False

        # Rolling success rate (only meaningful once window is full)
        with self._stats_lock:
            window_full = len(self._success_window) >= svc.fps_window
        if window_full and self._success_rate() < svc.success_rate_min:
            return False

        # FPS drop (only after warm-up)
        fps = self.fps_actual()
        if fps > 0 and fps < self._cam_cfg.target_fps * svc.fps_drop_ratio:
            return False

        return True

    def _set_state(self, new: CameraState) -> None:
        """Transition state and fire callback.  Caller must hold _state_lock."""
        if self._state == new:
            return
        old, self._state = self._state, new
        log.debug("CameraService: %s → %s", old.name, new.name)
        cb = self._on_state_change
        if cb:
            try:
                cb(new)
            except Exception:
                log.exception("CameraService: on_state_change raised")

    # ──────────────────────────────────────────────────────────────────────────
    # Watchdog
    # ──────────────────────────────────────────────────────────────────────────

    def _start_watchdog(self) -> None:
        self._shutdown.clear()
        self._watchdog = threading.Thread(
            target=self._watchdog_loop,
            name="camera-watchdog",
            daemon=True,
        )
        self._watchdog.start()
        log.debug(
            "CameraService: watchdog started (interval=%.1fs)",
            self._svc_cfg.health_check_interval,
        )

    def _watchdog_loop(self) -> None:
        interval = self._svc_cfg.health_check_interval
        while not self._shutdown.wait(timeout=interval):
            try:
                self._probe_health()
            except Exception:
                log.exception("CameraService: watchdog probe error")
        log.debug("CameraService: watchdog exited")

    def _probe_health(self) -> None:
        # Only act when nominally RUNNING — never interrupt an in-flight recovery.
        if self._state != CameraState.RUNNING:
            return

        # 1. Hardware handle sanity
        with self._cap_lock:
            cap_ok = self._cap is not None and self._cap.isOpened()

        if not cap_ok:
            self._trigger_recovery("cap.isOpened() returned False")
            return

        # 2. Metric-based health check
        if not self._healthy():
            fps = self.fps_actual()
            sr  = self._success_rate()
            reason = (
                f"consecutive_failures={self._consec_failures}  "
                f"fps={fps:.1f}/{self._cam_cfg.target_fps}  "
                f"success_rate={sr:.2f}"
            )
            self._trigger_recovery(reason)

    def _trigger_recovery(self, reason: str) -> None:
        with self._state_lock:
            if self._state != CameraState.RUNNING:
                return   # already recovering or released — don't double-trigger
            self._last_error = reason
            self._total_recoveries += 1
            self._recovery_attempt = 0
            self._set_state(CameraState.RECOVERING)

        log.warning("CameraService: recovery triggered — %s", reason)

        cb = self._on_error
        if cb:
            try:
                cb(reason)
            except Exception:
                log.exception("CameraService: on_error raised")

        t = threading.Thread(
            target=self._recovery_loop,
            name="camera-recovery",
            daemon=True,
        )
        t.start()

    # ──────────────────────────────────────────────────────────────────────────
    # Recovery workflow
    # ──────────────────────────────────────────────────────────────────────────

    def _recovery_loop(self) -> None:
        """
        Exponential-backoff reopen loop.

        RECOVERING → (release → wait → reopen) × N
                  ↓ success           ↓ exhausted
                RUNNING              ERROR
        """
        svc = self._svc_cfg
        log.info("CameraService: recovery started (max_attempts=%d)", svc.max_recovery_attempts)

        while True:
            with self._state_lock:
                attempt = self._recovery_attempt

            if attempt >= svc.max_recovery_attempts:
                break

            backoff = min(
                svc.recovery_backoff_base * (2 ** attempt),
                svc.recovery_backoff_max,
            )
            log.info(
                "CameraService: recovery attempt %d/%d — waiting %.1fs",
                attempt + 1, svc.max_recovery_attempts, backoff,
            )

            # Interruptible wait — close() sets _shutdown
            if self._shutdown.wait(timeout=backoff):
                log.info("CameraService: recovery aborted (shutdown)")
                return

            # Close the broken cap before reopening
            with self._cap_lock:
                if self._cap is not None:
                    self._cap.release()
                    self._cap = None

            if self._open_cap():
                # Verify shutdown didn't race us to the finish
                if self._shutdown.is_set():
                    with self._cap_lock:
                        if self._cap:
                            self._cap.release()
                            self._cap = None
                    return

                with self._state_lock:
                    self._start_time = time.monotonic()
                    self._set_state(CameraState.RUNNING)
                    recovered_on = self._recovery_attempt + 1

                log.info(
                    "CameraService: recovered after %d attempt(s)",
                    recovered_on,
                )
                cb = self._on_recovery_success
                if cb:
                    try:
                        cb(recovered_on)
                    except Exception:
                        log.exception("CameraService: on_recovery_success raised")

                self._start_watchdog()
                return

            with self._state_lock:
                self._recovery_attempt += 1

        # All attempts exhausted
        log.error(
            "CameraService: recovery exhausted (%d attempts) — entering ERROR",
            svc.max_recovery_attempts,
        )
        with self._state_lock:
            self._last_error = (
                f"recovery exhausted ({svc.max_recovery_attempts} attempts)"
            )
            self._set_state(CameraState.ERROR)

        cb = self._on_error
        if cb:
            try:
                cb(self._last_error)
            except Exception:
                log.exception("CameraService: on_error raised (exhausted)")


# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ──────────────────────────────────────────────────────────────────────────────

_SERVICE: Optional[CameraService] = None
_service_lock = threading.Lock()


def get_service() -> Optional[CameraService]:
    """Return the active singleton, or None if not yet initialised."""
    return _SERVICE


def start_camera(
    camera_config: Optional[CameraConfig] = None,
    service_config: Optional[ServiceConfig] = None,
    *,
    on_state_change:     Optional[Callable[[CameraState], None]] = None,
    on_recovery_success: Optional[Callable[[int],          None]] = None,
    on_error:            Optional[Callable[[str],           None]] = None,
) -> bool:
    """Create and open the global CameraService. Idempotent. Returns True on success."""
    global _SERVICE
    with _service_lock:
        if _SERVICE is not None and _SERVICE.state == CameraState.RUNNING:
            return True
        svc = CameraService(
            camera_config, service_config,
            on_state_change=on_state_change,
            on_recovery_success=on_recovery_success,
            on_error=on_error,
        )
        ok = svc.open()
        if ok:
            _SERVICE = svc
        return ok


def stop_camera() -> None:
    """Close and destroy the global CameraService."""
    global _SERVICE
    with _service_lock:
        if _SERVICE is not None:
            _SERVICE.close()
            _SERVICE = None


def read_frame() -> Optional[np.ndarray]:
    """Read one raw frame from the global CameraService (None on failure)."""
    svc = _SERVICE
    return svc.read() if svc is not None else None


def camera_health() -> Optional[CameraHealth]:
    """Return a health snapshot from the global CameraService."""
    svc = _SERVICE
    return svc.get_health() if svc is not None else None
