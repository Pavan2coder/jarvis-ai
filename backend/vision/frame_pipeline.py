"""
FramePipeline: a modular, ordered chain of per-frame processors.

Every frame captured by VisionManager passes through ONE shared pipeline before
it is distributed to subscribers. This is distinct from VisionManager's
per-subscriber ``_preprocess`` step:

    read() ─► FramePipeline.run()  ─►  _preprocess(cfg)  ─► subscriber
              (global, once/frame)     (per-subscriber:      (gesture, ocr, …)
               validate, timestamp,      flip, resize,
               metadata, [denoise…])     grayscale)

Why two stages?
───────────────
  • Global concerns (validation, timestamping, metadata, denoise) are the SAME
    for every consumer — compute them once, not once per subscriber, and every
    subscriber sees a consistent frame_id + timestamp.
  • Per-consumer concerns (fps limit, resolution, color, flip) differ per
    subscriber, so each subscriber gets its own chain of the SAME processor type,
    assembled from its SubscriberConfig (VisionManager.build_subscriber_pipeline)
    and run via ``apply()`` against a derived copy of the global context.

Open/Closed
───────────
  Add a new stage by writing a FrameProcessor subclass and calling
  ``pipeline.add(MyProcessor())``. No existing code is modified. Stages run in
  insertion order; each may transform the frame, annotate ``ctx.metadata``, or
  drop the frame entirely (return None).

Backward compatibility
───────────────────────
  ``default_pipeline()`` enables only pixel-preserving stages (validate →
  timestamp → metadata). Existing subscribers (gesture, OCR) and pull consumers
  (camera_ops, virtual_keyboard) therefore receive byte-identical frames to the
  pre-pipeline behaviour. NoiseReducer is a global opt-in (add it to enable).
  The per-subscriber stages only run when a subscriber's config requests them,
  so a subscriber with no transforms still receives an unaltered frame copy.

Thread-safety
─────────────
  ``run()`` executes on VisionManager's single capture thread. add()/remove()/
  stages() are guarded by a lock so the pipeline can be reconfigured at runtime.
  Processors themselves must be stateless or internally thread-safe.
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

log = logging.getLogger("JARVIS.vision.pipeline")


# ──────────────────────────────────────────────────────────────────────────────
# Per-frame context — carries metadata/timestamps down the chain
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class FrameContext:
    """
    Mutable per-frame scratch space passed to every processor.

    frame_id:      monotonically increasing counter assigned by the pipeline.
    capture_wall:  wall-clock time of capture (time.time()); for logging/EXIF.
    capture_mono:  monotonic timestamp (time.monotonic()); for latency math.
    metadata:      free-form dict any stage may write to (shape, fps, tags…).
    """
    frame_id: int
    capture_wall: float
    capture_mono: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def derive(self) -> "FrameContext":
        """
        Return a per-subscriber copy sharing this frame's id/timestamps but with
        an independent metadata dict. Per-subscriber stages (flip/scale/color)
        annotate the copy, so they never pollute the global metadata exposed by
        VisionManager.get_latest_metadata().
        """
        return FrameContext(
            frame_id=self.frame_id,
            capture_wall=self.capture_wall,
            capture_mono=self.capture_mono,
            metadata=dict(self.metadata),
        )


@dataclass
class ProcessedFrame:
    """Output of a full pipeline run: the (possibly transformed) frame + context."""
    frame: np.ndarray
    context: FrameContext


# ──────────────────────────────────────────────────────────────────────────────
# Processor interface — the extension point
# ──────────────────────────────────────────────────────────────────────────────

class FrameProcessor(ABC):
    """
    One stage in the pipeline.

    Implement ``process`` to transform the frame and/or annotate ``ctx``.
    Return the frame to pass downstream, or ``None`` to drop it (the whole
    frame is discarded and never distributed — used by validation).

    Contract:
      • Must not block. This runs on the capture thread; slow work here lowers
        the effective capture rate for ALL subscribers.
      • Should be stateless or internally thread-safe.
      • ``enabled = False`` makes the pipeline skip the stage without removing it.
    """

    #: stable identifier, unique within a pipeline
    name: str = "processor"
    #: toggle without removing from the chain
    enabled: bool = True

    @abstractmethod
    def process(
        self, frame: np.ndarray, ctx: FrameContext
    ) -> Optional[np.ndarray]:
        raise NotImplementedError


# ──────────────────────────────────────────────────────────────────────────────
# The pipeline
# ──────────────────────────────────────────────────────────────────────────────

class FramePipeline:
    """Ordered, runtime-reconfigurable chain of FrameProcessors."""

    def __init__(self, stages: Optional[List[FrameProcessor]] = None) -> None:
        self._stages: List[FrameProcessor] = list(stages or [])
        self._lock = threading.RLock()
        self._next_id: int = 0

    # ---- composition (Open/Closed extension API) -----------------------------

    def add(self, processor: FrameProcessor, index: Optional[int] = None) -> None:
        """Append a stage (or insert at ``index``). Safe at runtime."""
        with self._lock:
            if index is None:
                self._stages.append(processor)
            else:
                self._stages.insert(index, processor)
        log.info("Pipeline stage %r added (enabled=%s)", processor.name, processor.enabled)

    def remove(self, name: str) -> bool:
        """Remove the first stage matching ``name``. Returns True if removed."""
        with self._lock:
            for i, s in enumerate(self._stages):
                if s.name == name:
                    del self._stages[i]
                    log.info("Pipeline stage %r removed", name)
                    return True
        return False

    def get(self, name: str) -> Optional[FrameProcessor]:
        with self._lock:
            for s in self._stages:
                if s.name == name:
                    return s
        return None

    def set_enabled(self, name: str, enabled: bool) -> bool:
        stage = self.get(name)
        if stage is None:
            return False
        stage.enabled = enabled
        log.info("Pipeline stage %r enabled=%s", name, enabled)
        return True

    def stage_names(self) -> List[str]:
        with self._lock:
            return [s.name for s in self._stages]

    # ---- execution -----------------------------------------------------------

    def run(self, frame: np.ndarray) -> Optional[ProcessedFrame]:
        """
        Run the chain against a NEW context (assigns frame_id + timestamps).

        Used by VisionManager for the global, once-per-frame pass. Returns a
        ProcessedFrame, or None if a stage dropped the frame (e.g. validation).

        Runs on VisionManager's capture thread.
        """
        with self._lock:
            fid = self._next_id
            self._next_id += 1

        ctx = FrameContext(
            frame_id=fid,
            capture_wall=time.time(),
            capture_mono=time.monotonic(),
        )
        out = self.apply(frame, ctx)
        return None if out is None else ProcessedFrame(frame=out, context=ctx)

    def apply(self, frame: np.ndarray, ctx: FrameContext) -> Optional[np.ndarray]:
        """
        Run every enabled stage in order against an EXISTING context.

        Used by VisionManager for per-subscriber chains, which reuse the global
        frame's context (via ctx.derive()) rather than minting a new one.

        Returns the transformed frame, or None if a stage dropped it (e.g. the
        FPS limiter gated this frame). A stage that RAISES is logged and skipped —
        the frame continues down the chain unchanged, never killing the caller.
        """
        with self._lock:
            stages = list(self._stages)  # snapshot; run outside the lock

        current = frame
        for stage in stages:
            if not stage.enabled:
                continue
            try:
                out = stage.process(current, ctx)
            except Exception:
                log.exception("Pipeline stage %r raised — skipping stage", stage.name)
                continue
            if out is None:
                log.debug("Pipeline stage %r dropped frame %d", stage.name, ctx.frame_id)
                return None
            current = out

        return current


# ──────────────────────────────────────────────────────────────────────────────
# Built-in stages — DEFAULT-ON (pixel-preserving, backward compatible)
# ──────────────────────────────────────────────────────────────────────────────

class FrameValidator(FrameProcessor):
    """
    Reject malformed frames before anything downstream touches them.

    Drops (returns None) frames that are None, empty, or not a 2-D/3-D uint8
    ndarray. Keeps a single buggy capture from crashing subscribers.
    """
    name = "validate"

    def process(self, frame: np.ndarray, ctx: FrameContext) -> Optional[np.ndarray]:
        if frame is None or not isinstance(frame, np.ndarray):
            return None
        if frame.size == 0 or frame.ndim not in (2, 3):
            return None
        return frame


class Timestamper(FrameProcessor):
    """
    Record capture timestamps into metadata. Pixel-preserving.

    (FrameContext already stamps capture_wall/capture_mono at run() start; this
    stage surfaces them into metadata so downstream metadata consumers see them
    in one place, and marks when the frame cleared validation.)
    """
    name = "timestamp"

    def process(self, frame: np.ndarray, ctx: FrameContext) -> np.ndarray:
        ctx.metadata["capture_wall"] = ctx.capture_wall
        ctx.metadata["capture_mono"] = ctx.capture_mono
        return frame


class MetadataGenerator(FrameProcessor):
    """
    Attach shape/format facts to metadata. Pixel-preserving.

    Populates: frame_id, width, height, channels, dtype.
    """
    name = "metadata"

    def process(self, frame: np.ndarray, ctx: FrameContext) -> np.ndarray:
        h, w = frame.shape[:2]
        ctx.metadata["frame_id"] = ctx.frame_id
        ctx.metadata["width"] = int(w)
        ctx.metadata["height"] = int(h)
        ctx.metadata["channels"] = int(frame.shape[2]) if frame.ndim == 3 else 1
        ctx.metadata["dtype"] = str(frame.dtype)
        return frame


# ──────────────────────────────────────────────────────────────────────────────
# Built-in stages — GLOBAL opt-in (not in default_pipeline; add to enable)
# ──────────────────────────────────────────────────────────────────────────────

class NoiseReducer(FrameProcessor):
    """
    Gaussian blur denoise. Not in the default pipeline — add to enable.

    Runs globally (once per frame). Note: light denoise can HURT MediaPipe
    landmark precision, so with gesture as a subscriber prefer leaving this off
    or scoping it per-subscriber.
    """
    name = "noise_reduction"

    def __init__(self, ksize: Tuple[int, int] = (3, 3), sigma: float = 0.0) -> None:
        self.ksize = ksize
        self.sigma = sigma

    def process(self, frame: np.ndarray, ctx: FrameContext) -> np.ndarray:
        out = cv2.GaussianBlur(frame, self.ksize, self.sigma)
        ctx.metadata["denoised"] = True
        return out


# ──────────────────────────────────────────────────────────────────────────────
# Built-in stages — PER-SUBSCRIBER (assembled from SubscriberConfig)
#
# These run in each subscriber's own chain, not globally, because the right
# value differs per consumer (gesture flips + keeps BGR; a future OCR would use
# grayscale, unflipped). VisionManager.build_subscriber_pipeline wires them up.
# ──────────────────────────────────────────────────────────────────────────────

class FpsLimiter(FrameProcessor):
    """
    Per-subscriber frame-rate gate. Placed FIRST in a subscriber's chain so
    gated frames are dropped before any transform work is spent on them.

    Stateful (tracks the last delivery time) — one instance per subscriber,
    only ever called from the single capture thread, so no lock is needed.
    """
    name = "fps_limiter"

    def __init__(self, fps_limit: Optional[float]) -> None:
        self._min_interval = (1.0 / fps_limit) if fps_limit else 0.0
        self._last_ts = 0.0

    def process(self, frame: np.ndarray, ctx: FrameContext) -> Optional[np.ndarray]:
        if self._min_interval <= 0.0:
            return frame
        now = ctx.capture_mono
        if (now - self._last_ts) < self._min_interval:
            return None  # gated — drop this frame for this subscriber
        self._last_ts = now
        return frame


class ResolutionScaler(FrameProcessor):
    """Resize a frame to a fixed (width, height). Per-subscriber."""
    name = "resolution_scale"

    def __init__(self, size: Tuple[int, int], interpolation: int = cv2.INTER_AREA) -> None:
        self.size = size
        self.interpolation = interpolation

    def process(self, frame: np.ndarray, ctx: FrameContext) -> np.ndarray:
        out = cv2.resize(frame, self.size, interpolation=self.interpolation)
        ctx.metadata["scaled_to"] = self.size
        return out


class ColorConverter(FrameProcessor):
    """
    Color-space conversion (e.g. BGR→GRAY). Per-subscriber.

    Deliberately never global: gesture (MediaPipe) needs 3-channel BGR and photo
    capture expects BGR, so a shared grayscale would break them.
    """
    name = "color_convert"

    def __init__(self, code: int = cv2.COLOR_BGR2GRAY) -> None:
        self.code = code

    def process(self, frame: np.ndarray, ctx: FrameContext) -> np.ndarray:
        out = cv2.cvtColor(frame, self.code)
        ctx.metadata["color_converted"] = self.code
        return out


class HorizontalFlip(FrameProcessor):
    """
    Mirror the frame left-right. Per-subscriber.

    True for gesture (selfie view); False for OCR/face (mirroring reverses text
    and lateralises face descriptors).
    """
    name = "horizontal_flip"

    def process(self, frame: np.ndarray, ctx: FrameContext) -> np.ndarray:
        out = cv2.flip(frame, 1)
        ctx.metadata["flipped"] = True
        return out


# ──────────────────────────────────────────────────────────────────────────────
# Default factory
# ──────────────────────────────────────────────────────────────────────────────

def default_pipeline() -> FramePipeline:
    """
    The pipeline VisionManager uses out of the box.

    Only pixel-preserving stages are enabled, so every existing consumer
    receives byte-identical frames to the pre-pipeline behaviour:

        validate → timestamp → metadata
    """
    return FramePipeline([
        FrameValidator(),
        Timestamper(),
        MetadataGenerator(),
    ])
