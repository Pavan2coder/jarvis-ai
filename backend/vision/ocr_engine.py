"""
OCREngine — Tesseract-backed text extraction for Jarvis OS.

Dual operating mode
───────────────────
  Push:     subscribe to VisionManager → receive grayscale frames → extract
            text continuously at 5 fps.
  One-shot: call extract_text(frame) or capture_screen() at any time without
            an active subscription.

Architecture
────────────
  [Camera] → VisionManager
                 │  SubscriberConfig(fps_limit=5, flip_horizontal=False, grayscale=True)
                 ▼
           OCREngine._on_frame(gray_frame)        ← subscriber worker thread
                 │
         ┌───────┴───────────┐
    _crop_region(region)   _preprocess(cfg)
         │                   │  upscale → denoise → binarize
         └───────┬───────────┘
                 ▼
         pytesseract.image_to_data()
                 │
         ┌───────┴───────────┐
    OCRResult (stored)   callbacks (on text change)
         │
   get_latest_result()    ← pull-style access from any thread

One-shot API (no subscription required)
────────────────────────────────────────
   result = ocr_engine.extract_text(frame, region)
   result = ocr_engine.capture_screen(region)    # requires: pip install mss

Dependencies
────────────
   pip install pytesseract
   Tesseract binary:
     Windows — https://github.com/UB-Mannheim/tesseract/wiki
     Linux   — apt install tesseract-ocr
   pip install mss    # optional — only for capture_screen()

Configuration
─────────────
   Set JARVIS_TESSERACT_CMD in your .env to override the binary path:
   JARVIS_TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np

try:
    import pytesseract
    _TESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None  # type: ignore[assignment]
    _TESSERACT_AVAILABLE = False

from backend.utils.logger import logger


# ──────────────────────────────────────────────────────────────────────────────
# Configuration & data types
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class OCRConfig:
    """
    OCR tuning policy.

    lang:                 Tesseract language pack(s). Comma-separated: "eng+fra".
    psm:                  Page segmentation mode.
                            3  = auto (default, good for unknown layouts)
                            6  = single uniform block (documents/cards)
                            11 = sparse text (camera frames, stickers, labels)
    confidence_threshold: Words with confidence below this (0–100) are dropped.
    min_word_length:      Minimum character count per accepted word (noise filter).
    scale_factor:         Upscale before OCR. 2.0 lifts a 640 px frame to ~300 DPI.
    denoise:              Gaussian blur (3×3) before binarization.
    binarize:             OTSU threshold — improves accuracy on camera frames.
    tesseract_cmd:        Explicit path to the Tesseract binary.
                          None → read JARVIS_TESSERACT_CMD env var, then auto-detect.
    """
    lang: str = "eng"
    psm: int = 3
    confidence_threshold: float = 40.0
    min_word_length: int = 2
    scale_factor: float = 2.0
    denoise: bool = True
    binarize: bool = True
    tesseract_cmd: Optional[str] = None


@dataclass
class OCRRegion:
    """
    Normalized (0.0–1.0) rectangular sub-region of a frame or screen.
    Applied before preprocessing so OCR focuses only on the target area.

    For camera frames:   fraction of the captured frame dimensions.
    For screen capture:  fraction of the primary monitor dimensions.
    """
    x: float        # left edge
    y: float        # top edge
    width: float    # region width
    height: float   # region height

    @classmethod
    def from_pixels(
        cls,
        px: int, py: int, pw: int, ph: int,
        frame_width: int, frame_height: int,
    ) -> "OCRRegion":
        """Convenience constructor from absolute pixel coordinates."""
        return cls(
            x=px / frame_width,
            y=py / frame_height,
            width=pw / frame_width,
            height=ph / frame_height,
        )


@dataclass
class WordResult:
    """Per-word OCR output with bounding box in the (possibly cropped) image."""
    text: str
    confidence: float                    # 0.0–100.0, Tesseract native
    bbox: Tuple[int, int, int, int]      # (left, top, width, height) in pixels


@dataclass
class OCRResult:
    """Complete extraction result for one frame or one-shot call."""
    text: str                            # accepted words joined with spaces
    words: List[WordResult]              # per-word detail (confidence ≥ threshold)
    mean_confidence: float               # average confidence of accepted words
    frame_count: int                     # monotonic counter (0 for one-shot calls)
    region: Optional[OCRRegion]          # scanned sub-region; None = full frame
    processing_time_ms: float            # wall-clock time for this OCR call

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


class OCRState(str, Enum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    ERROR   = "ERROR"


# ──────────────────────────────────────────────────────────────────────────────
# Frame utilities  (module-level so they're usable without an engine instance)
# ──────────────────────────────────────────────────────────────────────────────

def _ensure_grayscale(frame: np.ndarray) -> np.ndarray:
    if len(frame.shape) == 3:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return frame


def _crop_region(frame: np.ndarray, region: OCRRegion) -> np.ndarray:
    h, w = frame.shape[:2]
    x1 = max(0, int(region.x * w))
    y1 = max(0, int(region.y * h))
    x2 = min(w, int((region.x + region.width) * w))
    y2 = min(h, int((region.y + region.height) * h))
    if x2 <= x1 or y2 <= y1:
        return frame   # degenerate region — fall back to full frame
    return frame[y1:y2, x1:x2]


def _preprocess(frame: np.ndarray, cfg: OCRConfig) -> np.ndarray:
    """Upscale, denoise, and binarize a grayscale frame before Tesseract."""
    out = frame
    if cfg.scale_factor != 1.0:
        h, w = out.shape[:2]
        out = cv2.resize(
            out,
            (int(w * cfg.scale_factor), int(h * cfg.scale_factor)),
            interpolation=cv2.INTER_CUBIC,
        )
    if cfg.denoise:
        out = cv2.GaussianBlur(out, (3, 3), 0)
    if cfg.binarize:
        _, out = cv2.threshold(out, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return out


def _capture_screen(region: Optional[OCRRegion] = None) -> Optional[np.ndarray]:
    """
    Capture the primary monitor (or a sub-region) as a BGR ndarray.

    When region is provided, mss captures only those pixels — more efficient
    than full-screen grab + crop.

    Returns None if mss is not installed or capture fails.
    """
    try:
        import mss  # noqa: PLC0415
        with mss.mss() as sct:
            monitor = dict(sct.monitors[1])   # copy — don't mutate mss internals
            if region is not None:
                monitor = {
                    "top":    monitor["top"]  + int(region.y      * monitor["height"]),
                    "left":   monitor["left"] + int(region.x      * monitor["width"]),
                    "width":  int(region.width  * monitor["width"]),
                    "height": int(region.height * monitor["height"]),
                }
            shot = sct.grab(monitor)
            return cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)
    except ImportError:
        logger.warning("OCR screen capture requires 'mss' — pip install mss")
        return None
    except Exception as e:
        logger.error("OCR screen capture failed: %s", e)
        return None


def _empty_result(
    frame_count: int = 0,
    region: Optional[OCRRegion] = None,
) -> OCRResult:
    return OCRResult(
        text="", words=[], mean_confidence=0.0,
        frame_count=frame_count, region=region, processing_time_ms=0.0,
    )


# ──────────────────────────────────────────────────────────────────────────────
# OCR Engine
# ──────────────────────────────────────────────────────────────────────────────

class OCREngine:
    """
    Tesseract text extractor with VisionManager integration.

    Thread model
    ────────────
    _on_frame() executes on VisionManager's subscriber worker thread.
    extract_text(), capture_screen(), and get_latest_result() are safe to
    call from any thread.
    """

    def __init__(self, config: Optional[OCRConfig] = None) -> None:
        self._config = config or OCRConfig()
        self._running = False
        self._state = OCRState.STOPPED
        self._state_lock = threading.Lock()

        self._latest_result: Optional[OCRResult] = None
        self._result_lock = threading.Lock()

        self._callbacks: List[Callable[[OCRResult], None]] = []
        self._callbacks_lock = threading.Lock()

        self._frame_count: int = 0
        self._last_text_hash: Optional[int] = None

        self._configure_tesseract()

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Subscribe to VisionManager and begin continuous text extraction."""
        if self._running:
            return True

        if not _TESSERACT_AVAILABLE:
            logger.error("OCREngine: pytesseract not installed — pip install pytesseract")
            self._set_state(OCRState.ERROR)
            return False

        # Probe the binary before committing to the subscriber
        try:
            pytesseract.get_tesseract_version()
        except pytesseract.TesseractNotFoundError as e:
            logger.error("OCREngine: Tesseract binary not found — %s", e)
            self._set_state(OCRState.ERROR)
            return False

        from backend.vision.vision_manager import subscribe, SubscriberConfig
        subscribe(
            "ocr",
            self._on_frame,
            SubscriberConfig(fps_limit=5, flip_horizontal=False, grayscale=True),
        )

        self._running = True
        self._set_state(OCRState.RUNNING)
        logger.info("OCREngine started (continuous mode, 5 fps).")
        return True

    def stop(self) -> None:
        """Unsubscribe from VisionManager and clear stored state."""
        if not self._running:
            return

        self._running = False

        from backend.vision.vision_manager import unsubscribe
        unsubscribe("ocr")

        with self._result_lock:
            self._latest_result = None

        self._set_state(OCRState.STOPPED)
        logger.info("OCREngine stopped.")

    @property
    def state(self) -> OCRState:
        with self._state_lock:
            return self._state

    def _set_state(self, state: OCRState) -> None:
        with self._state_lock:
            self._state = state

    # ── result access ──────────────────────────────────────────────────────────

    def get_latest_result(self) -> Optional[OCRResult]:
        """Pull the most recent OCRResult from continuous mode. Thread-safe."""
        with self._result_lock:
            return self._latest_result

    # ── change callbacks ───────────────────────────────────────────────────────

    def register_callback(self, cb: Callable[[OCRResult], None]) -> None:
        """
        Register a function invoked when new non-empty text is detected.

        Deduped by full-text hash — fires only when content actually changes,
        not on every frame. The callback runs on VisionManager's subscriber
        worker thread; dispatch to your own thread if needed.
        """
        with self._callbacks_lock:
            if cb not in self._callbacks:
                self._callbacks.append(cb)

    def unregister_callback(self, cb: Callable[[OCRResult], None]) -> None:
        with self._callbacks_lock:
            self._callbacks = [c for c in self._callbacks if c is not cb]

    # ── one-shot API ───────────────────────────────────────────────────────────

    def extract_text(
        self,
        frame: np.ndarray,
        region: Optional[OCRRegion] = None,
    ) -> OCRResult:
        """
        Synchronous, one-shot OCR on any numpy frame (BGR or grayscale).
        Does not require an active VisionManager subscription.
        Thread-safe; safe to call from any thread.
        """
        if not _TESSERACT_AVAILABLE:
            logger.error("OCREngine.extract_text: pytesseract not installed.")
            return _empty_result(region=region)
        return self._run_ocr(frame, region, frame_count=0)

    def capture_screen(
        self,
        region: Optional[OCRRegion] = None,
    ) -> Optional[OCRResult]:
        """
        Capture the primary monitor and extract text.
        region: OCRRegion in normalized screen coordinates, or None for full screen.
        Requires mss (pip install mss); returns None if unavailable.
        """
        frame = _capture_screen(region)  # mss handles the region crop
        if frame is None:
            return None
        if not _TESSERACT_AVAILABLE:
            logger.error("OCREngine.capture_screen: pytesseract not installed.")
            return _empty_result(region=region)
        # region already applied by _capture_screen; pass None to avoid double-crop
        return self._run_ocr(frame, region=None, frame_count=0)

    # ── subscriber callback ────────────────────────────────────────────────────

    def _on_frame(self, frame: np.ndarray) -> None:
        """
        Push callback from VisionManager's subscriber worker thread.
        Frame arrives as single-channel grayscale at ≤5 fps.
        flip_horizontal=False — text must not be mirrored.
        """
        if not self._running:
            return

        self._frame_count += 1
        result = self._run_ocr(frame, region=None, frame_count=self._frame_count)

        with self._result_lock:
            self._latest_result = result

        if result.has_text:
            text_hash = hash(result.text)
            if text_hash != self._last_text_hash:
                self._last_text_hash = text_hash
                self._fire_callbacks(result)

    def _fire_callbacks(self, result: OCRResult) -> None:
        with self._callbacks_lock:
            cbs = list(self._callbacks)
        for cb in cbs:
            try:
                cb(result)
            except Exception as e:
                logger.error("OCR result callback raised: %s", e)

    # ── core extraction ────────────────────────────────────────────────────────

    def _run_ocr(
        self,
        frame: np.ndarray,
        region: Optional[OCRRegion],
        frame_count: int,
    ) -> OCRResult:
        t_start = time.monotonic()

        gray = _ensure_grayscale(frame)
        cropped = _crop_region(gray, region) if region else gray
        processed = _preprocess(cropped, self._config)

        try:
            data = pytesseract.image_to_data(
                processed,
                lang=self._config.lang,
                config=f"--psm {self._config.psm}",
                output_type=pytesseract.Output.DICT,
            )
        except pytesseract.TesseractError as e:
            logger.error("OCR extraction failed: %s", e)
            return _empty_result(frame_count=frame_count, region=region)

        words: List[WordResult] = []
        accepted: List[str] = []

        for i, raw in enumerate(data["text"]):
            conf = float(data["conf"][i])
            if conf < 0:
                continue   # conf == -1: block/line/paragraph marker, not a word
            word = raw.strip()
            if len(word) < self._config.min_word_length:
                continue
            if conf >= self._config.confidence_threshold:
                accepted.append(word)
                words.append(WordResult(
                    text=word,
                    confidence=conf,
                    bbox=(
                        data["left"][i], data["top"][i],
                        data["width"][i], data["height"][i],
                    ),
                ))

        mean_conf = sum(w.confidence for w in words) / len(words) if words else 0.0

        return OCRResult(
            text=" ".join(accepted),
            words=words,
            mean_confidence=round(mean_conf, 1),
            frame_count=frame_count,
            region=region,
            processing_time_ms=round((time.monotonic() - t_start) * 1000.0, 1),
        )

    # ── Tesseract binary configuration ─────────────────────────────────────────

    def _configure_tesseract(self) -> None:
        if not _TESSERACT_AVAILABLE:
            return

        # Priority: explicit OCRConfig override > JARVIS_TESSERACT_CMD env var
        #           > Windows auto-detect common install path
        cmd = (
            self._config.tesseract_cmd
            or os.environ.get("JARVIS_TESSERACT_CMD")
        )
        if cmd is None and os.name == "nt":
            win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.isfile(win_path):
                cmd = win_path

        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd
            logger.debug("Tesseract binary: %s", cmd)


# ──────────────────────────────────────────────────────────────────────────────
# Module-level singleton  (mirrors gesture_engine.ENGINE / audio_engine.ENGINE)
# ──────────────────────────────────────────────────────────────────────────────

ENGINE: Optional[OCREngine] = None


def start_ocr(config: Optional[OCRConfig] = None) -> bool:
    """
    Initialize and start the shared OCREngine.
    Subscribes to VisionManager — call start_vision() first.
    Idempotent if ENGINE is already running.
    """
    global ENGINE
    if ENGINE is None:
        ENGINE = OCREngine(config)
    return ENGINE.start()


def stop_ocr() -> None:
    """Unsubscribe from VisionManager and stop the shared OCREngine."""
    global ENGINE
    if ENGINE is not None:
        ENGINE.stop()


def extract_text(
    frame: np.ndarray,
    region: Optional[OCRRegion] = None,
) -> OCRResult:
    """
    One-shot text extraction from a frame.
    Creates ENGINE if needed but does NOT subscribe to VisionManager.
    Thread-safe.
    """
    global ENGINE
    if ENGINE is None:
        ENGINE = OCREngine()
    return ENGINE.extract_text(frame, region)


def capture_screen(region: Optional[OCRRegion] = None) -> Optional[OCRResult]:
    """
    One-shot OCR on the primary monitor.
    Creates ENGINE if needed. Requires mss (pip install mss).
    """
    global ENGINE
    if ENGINE is None:
        ENGINE = OCREngine()
    return ENGINE.capture_screen(region)


def get_latest_result() -> Optional[OCRResult]:
    """Pull the latest continuous-mode OCRResult. None if engine not running."""
    if ENGINE is None:
        return None
    return ENGINE.get_latest_result()


# ──────────────────────────────────────────────────────────────────────────────
# INTEGRATION EXAMPLES
# ──────────────────────────────────────────────────────────────────────────────
#
# ── 1. Boot wiring in backend/main.py ─────────────────────────────────────────
#
#   from backend.vision.vision_manager import start_vision
#   from backend.vision.ocr_engine import start_ocr, stop_ocr
#   from core.shutdown_manager import shutdown_manager
#
#   # VisionManager must be running before any subscriber can receive frames.
#   start_vision()
#
#   # OCR subscribes at priority 30 — same tier as gesture_engine.
#   # stop_ocr before stop_vision (subscriber must unsubscribe before camera closes).
#   shutdown_manager.register_handler("ocr_engine", stop_ocr, priority=30)
#
#   # Start continuous OCR (optional — only if you want background scanning).
#   start_ocr()
#
#
# ── 2. Continuous mode — react to detected text ────────────────────────────────
#
#   from backend.vision.ocr_engine import start_ocr, ENGINE
#
#   def on_text(result):
#       print(f"[OCR] {result.text!r}  conf={result.mean_confidence:.0f}%"
#             f"  ({result.processing_time_ms:.0f} ms)")
#
#   start_ocr()
#   ENGINE.register_callback(on_text)
#
#   # Pull-style alternative (e.g. polled by a status endpoint):
#   from backend.vision.ocr_engine import get_latest_result
#   result = get_latest_result()
#   if result and result.has_text:
#       print(result.text)
#
#
# ── 3. One-shot — read text from a camera frame ────────────────────────────────
#
#   import cv2
#   from backend.vision.ocr_engine import extract_text, OCRRegion
#
#   frame = cv2.imread("document.png")
#
#   # Full frame
#   result = extract_text(frame)
#   print(result.text)
#
#   # Crop to the top-right quarter only
#   roi = OCRRegion(x=0.5, y=0.0, width=0.5, height=0.5)
#   result = extract_text(frame, region=roi)
#   print(result.text)
#
#   # Per-word breakdown
#   for word in result.words:
#       print(f"  {word.text!r:20s}  conf={word.confidence:.0f}%  bbox={word.bbox}")
#
#
# ── 4. Screen region capture ───────────────────────────────────────────────────
#
#   from backend.vision.ocr_engine import capture_screen, OCRRegion
#
#   # Read the top-left corner of the screen (e.g. taskbar / title area)
#   corner = OCRRegion(x=0.0, y=0.0, width=0.3, height=0.1)
#   result = capture_screen(region=corner)
#   if result:
#       print(result.text)
#
#
# ── 5. Pixel-based region from known UI coordinates ───────────────────────────
#
#   from backend.vision.ocr_engine import extract_text, OCRRegion
#   from backend.vision.vision_manager import get_latest_frame
#
#   frame = get_latest_frame()
#   if frame is not None:
#       h, w = frame.shape[:2]
#       # Scan a 200×50 area starting at pixel (100, 80)
#       roi = OCRRegion.from_pixels(100, 80, 200, 50, w, h)
#       result = extract_text(frame, region=roi)
#       print(result.text)
#
#
# ── 6. Voice command trigger: "read what's on screen" ─────────────────────────
#
#   from backend.vision.ocr_engine import capture_screen
#
#   def cmd_read_screen(speak):
#       result = capture_screen()
#       if result and result.has_text:
#           speak(f"I can see: {result.text}")
#       else:
#           speak("I couldn't read any text on the screen.")
#
#
# ── 7. OCR on VisionManager latest frame (no subscription overhead) ────────────
#
#   from backend.vision.vision_manager import get_latest_frame
#   from backend.vision.ocr_engine import extract_text
#
#   frame = get_latest_frame()
#   if frame is not None:
#       result = extract_text(frame)
#       if result.has_text:
#           print(result.text, f"(conf={result.mean_confidence:.0f}%)")
