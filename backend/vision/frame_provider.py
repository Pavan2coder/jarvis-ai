"""
FrameProvider: hardware abstraction for video frame acquisition.

Wraps cv2.VideoCapture (webcam index or file/URL) behind a minimal interface.
All frames returned are canonical — no flip, no color conversion. Per-subscriber
preprocessing is VisionManager's responsibility.

Owned exclusively by VisionManager's capture thread — not thread-safe on its own.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Tuple, Union

import cv2
import numpy as np

log = logging.getLogger("JARVIS.vision.provider")


@dataclass
class CameraConfig:
    source: Union[int, str] = 0   # int = device index, str = file path / RTSP URL
    width: int = 640
    height: int = 480
    target_fps: int = 30


class FrameProvider:
    """
    Thin wrapper over cv2.VideoCapture.

    Using a string source (video file or RTSP URL) instead of an integer lets
    tests drive the pipeline with pre-recorded footage rather than real hardware.

        provider = FrameProvider(CameraConfig(source="test_data/hand_sample.mp4"))
    """

    def __init__(self, config: Optional[CameraConfig] = None) -> None:
        self._config = config or CameraConfig()
        self._cap: Optional[cv2.VideoCapture] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> bool:
        """Open the capture source. Returns True on success."""
        cfg = self._config
        self._cap = cv2.VideoCapture(cfg.source)
        if not self._cap.isOpened():
            log.error("Failed to open camera source %r", cfg.source)
            self._cap = None
            return False

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
        self._cap.set(cv2.CAP_PROP_FPS, cfg.target_fps)

        actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = self._cap.get(cv2.CAP_PROP_FPS)
        log.info(
            "Camera opened — source=%r  %dx%d  %.1f fps",
            cfg.source, actual_w, actual_h, actual_fps,
        )
        return True

    def close(self) -> None:
        """Release the capture device."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            log.info("Camera released — source=%r", self._config.source)

    # ------------------------------------------------------------------
    # Frame access
    # ------------------------------------------------------------------

    def read(self) -> Optional[np.ndarray]:
        """
        Return one raw, unprocessed frame (BGR, unflipped) or None on failure.
        Must only be called from the owning capture thread.
        """
        if self._cap is None:
            return None
        ret, frame = self._cap.read()
        return frame if ret else None

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    @property
    def resolution(self) -> Tuple[int, int]:
        if not self.is_open():
            return (0, 0)
        return (
            int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )

    @property
    def source(self) -> Union[int, str]:
        return self._config.source
