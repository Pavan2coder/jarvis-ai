import os
import time
import datetime
import cv2

from backend.core import config
from backend.vision.vision_manager import get_latest_frame, start_vision
from backend.vision.frame_provider import CameraConfig
from backend.utils.logger import logger

def capture_photo(save_dir=None) -> str:
    """
    Captures a frame from the shared VisionManager webcam and saves it.

    VisionManager is the single owner of the camera device. This pulls the latest
    frame from it (starting it if no vision feature has opened the camera yet)
    rather than opening its own competing cv2.VideoCapture, which would race the
    capture loop for the device and fail or return garbage on Windows.

    Returns:
        The absolute path to the saved image file if successful, otherwise None.
    """
    logger.info("Initializing camera capture...")

    # 1. Resolve save location
    if not save_dir:
        save_dir = config.FOLDERS.get("desktop", os.path.join(os.path.expanduser("~"), "Desktop"))

    if not os.path.exists(save_dir):
        try:
            os.makedirs(save_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create directory {save_dir}: {e}")
            return None

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"jarvis_photo_{timestamp}.png"
    filepath = os.path.join(save_dir, filename)

    # 2. Ensure the shared VisionManager owns/opens the camera. Idempotent — a
    #    no-op if gesture/OCR/face has already started it.
    cam_cfg = CameraConfig(source=getattr(config, "CAMERA_INDEX", 0))
    if not start_vision(cam_cfg):
        logger.error("VisionManager could not open the camera for capture.")
        return None

    # 3. Pull the latest frame, retrying briefly to let the capture loop warm up
    #    (auto-exposure + the first frames after a cold open).
    frame = None
    for _ in range(20):
        frame = get_latest_frame()
        if frame is not None:
            break
        time.sleep(0.1)

    if frame is None:
        logger.error("VisionManager is running but produced no frame to capture.")
        return None

    # 4. Save. VisionManager delivers a raw, unflipped BGR frame; mirror it so the
    #    saved photo matches the selfie-view the user sees on screen.
    frame = cv2.flip(frame, 1)
    try:
        success = cv2.imwrite(filepath, frame)
        if success:
            logger.info(f"Photo successfully saved to {filepath}")
            return filepath
        logger.error(f"cv2.imwrite failed to save to {filepath}")
    except Exception as e:
        logger.error(f"Exception during photo saving: {e}")

    return None
