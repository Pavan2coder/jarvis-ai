import os
import time
import datetime
import cv2

from backend.core import config
from backend.system import gesture_engine
from backend.utils.logger import logger

def capture_photo(save_dir=None) -> str:
    """
    Captures a frame from the webcam and saves it to the specified directory.
    If gesture control is currently running, it retrieves the frame thread-safely 
    from the running engine to prevent device conflicts. Otherwise, it spins up 
    a temporary capture stream, allows it to warm up, and captures the frame.
    
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
    
    frame = None
    
    # 2. Check if gesture engine is running and sharing its stream
    engine = gesture_engine.ENGINE
    if engine and engine.running:
        logger.info("Gesture engine is running. Retrieving frame from active stream.")
        # Try a few times to get a valid frame (to handle startup lag if any)
        for _ in range(10):
            frame = engine.get_latest_frame()
            if frame is not None:
                break
            time.sleep(0.1)
            
        if frame is None:
            logger.warning("Failed to retrieve frame from running gesture engine. Falling back to temporary capture.")
            
    # 3. Fallback/Default path: Open camera, capture, and close
    if frame is None:
        camera_idx = getattr(config, "CAMERA_INDEX", 0)
        logger.info(f"Opening webcam at index {camera_idx} for one-shot capture.")
        cap = cv2.VideoCapture(camera_idx)
        
        if not cap.isOpened():
            logger.error(f"Could not open webcam at index {camera_idx}.")
            return None
            
        try:
            # Warm up the camera (read multiple frames to let auto-exposure calibrate)
            for i in range(10):
                ret, temp_frame = cap.read()
                if ret:
                    frame = temp_frame
                time.sleep(0.05)
        except Exception as e:
            logger.error(f"Error during camera read: {e}")
        finally:
            cap.release()
            logger.info("Webcam released.")
            
    # 4. Save and return path
    if frame is not None:
        try:
            # OpenCV captures in BGR, which is fine for direct write. 
            # Make sure we flip if gesture engine isn't running and mirror image is preferred
            # (Webcams are usually mirrored, if we capture one-shot we can keep it standard or mirror it.
            # gesture_engine.py already flipped it, so if grabbed from gesture engine it is already flipped.)
            success = cv2.imwrite(filepath, frame)
            if success:
                logger.info(f"Photo successfully saved to {filepath}")
                return filepath
            else:
                logger.error(f"cv2.imwrite failed to save to {filepath}")
        except Exception as e:
            logger.error(f"Exception during photo saving: {e}")
            
    return None
