# J.A.R.V.I.S OS vision sub-package.

from backend.vision.frame_provider import CameraConfig, FrameProvider
from backend.vision.vision_manager import (
    MANAGER,
    SubscriberConfig,
    VisionManager,
    get_latest_frame,
    start_vision,
    stop_vision,
    subscribe,
    unsubscribe,
)
from backend.vision.ocr_engine import (
    OCRConfig,
    OCRRegion,
    OCRResult,
    OCRState,
    WordResult,
    capture_screen,
    extract_text,
    get_latest_result,
    start_ocr,
    stop_ocr,
)

__all__ = [
    # Vision manager
    "CameraConfig",
    "FrameProvider",
    "SubscriberConfig",
    "VisionManager",
    "MANAGER",
    "start_vision",
    "stop_vision",
    "subscribe",
    "unsubscribe",
    "get_latest_frame",
    # OCR engine
    "OCRConfig",
    "OCRRegion",
    "OCRResult",
    "OCRState",
    "WordResult",
    "capture_screen",
    "extract_text",
    "get_latest_result",
    "start_ocr",
    "stop_ocr",
]
