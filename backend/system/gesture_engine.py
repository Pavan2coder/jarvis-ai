import threading
import time
import cv2

from backend.core import config
from backend.vision.hand_tracking import HandTracker
from backend.vision.gesture_recognizer import classify_gesture
from backend.vision.gesture_actions import GestureActionsManager
from backend.vision.virtual_mouse import VirtualMouse
from backend.vision.profile_manager import profile_manager
from backend.vision.gesture_state import gesture_state_manager, GestureState
from backend.utils.logger import logger

# Shared singleton instance
ENGINE = None

class GestureEngine:
    def __init__(self):
        self.running = False
        self.thread = None
        self.cap = None
        self._latest_frame = None
        self._frame_lock = threading.Lock()
        
        # Core components
        self.tracker = HandTracker()
        self.mouse = VirtualMouse()
        self.actions = GestureActionsManager()
        
        # States
        self.camera_status = "Inactive"
        
    def start(self) -> bool:
        if self.running:
            return True
        if gesture_state_manager.prevent_duplicate_instances():
            logger.warning("Duplicate gesture start attempt blocked.")
            return False
            
        gesture_state_manager.transition_to(GestureState.STARTING)
        self.running = True
        self.camera_status = "Active"
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self.actions.emit_status("None", "None", self.running, self.camera_status)
        print("  🎥  Gesture Control Engine started.")
        return True

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.camera_status = "Inactive"
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
        with self._frame_lock:
            self._latest_frame = None
        self.mouse.release_mouse_safety()
        
        # Enforce transition to STOPPED state if not currently in ERROR
        if gesture_state_manager.get_state() != GestureState.ERROR:
            gesture_state_manager.transition_to(GestureState.STOPPED)
            
        self.actions.emit_status("None", "None", self.running, self.camera_status)
        print("  🎥  Gesture Control Engine stopped.")

    def get_latest_frame(self):
        """Thread-safe getter for the latest video frame."""
        if not self.running or self._latest_frame is None:
            return None
        with self._frame_lock:
            return self._latest_frame.copy()

    def _run_loop(self):
        has_error = False
        try:
            camera_idx = getattr(config, "CAMERA_INDEX", 0)
            self.cap = cv2.VideoCapture(camera_idx)
            if not self.cap.isOpened():
                print("  ⚠️  Could not open webcam for gesture control.")
                self.running = False
                self.camera_status = "Error"
                self.actions.emit_status("None", "None", self.running, self.camera_status)
                gesture_state_manager.transition_to(GestureState.ERROR, "Failed to open webcam.")
                return

            gesture_state_manager.transition_to(GestureState.RUNNING)

            while self.running:
                ret, frame = self.cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue
                
                # Flip horizontally to match mirror movement
                frame = cv2.flip(frame, 1)
                
                # Cache latest frame thread-safely (raw image for photos/camera_ops)
                with self._frame_lock:
                    self._latest_frame = frame.copy()
                    
                # Increment frame count in state manager
                gesture_state_manager.increment_frame_count()
                
                # Check for pause state
                fps = self.tracker.get_fps()
                if gesture_state_manager.get_state() == GestureState.PAUSED:
                    self.tracker.draw_overlays(frame, None, "PAUSED", "PAUSED", fps)
                    time.sleep(0.01)
                    continue
                    
                # Process hand tracking through MediaPipe
                results = self.tracker.process_frame(frame)
                
                gesture_name, action_name = "None", "None"
                
                if results and results.multi_hand_landmarks:
                    landmarks = results.multi_hand_landmarks[0].landmark
                    
                    # Extract classification confidence from MediaPipe results
                    confidence = 1.0
                    if results.multi_handedness:
                        confidence = results.multi_handedness[0].classification[0].score
                    
                    # Classify hand landmarks to gesture & action
                    raw_gesture, raw_action = classify_gesture(landmarks)
                    
                    # Stabilize gestures using history voting and confidence threshold
                    gesture_name, action_name = self.actions.stabilize_gesture_and_action(raw_gesture, raw_action, confidence)
                    
                    # Try executing discrete command actions (Mute, Play/Pause, Wake)
                    triggered = self.actions.execute_discrete_actions(
                        gesture_name, action_name, self.running, self.camera_status
                    )
                    
                    if not triggered:
                        # Execute continuous mouse movements and gestures dynamically based on profile mappings
                        mapping = profile_manager.get_mapping_for_gesture(gesture_name)
                        m_type = mapping.get("type", "none")
                        target = mapping.get("target", "none")
                        
                        if m_type == "mouse":
                            if target == "scroll":
                                self.mouse.handle_scrolling(landmarks)
                            elif target in ("move_cursor", "laser_pointer"):
                                self.mouse.reset_scroll()
                                self.mouse.move_cursor(landmarks[8])
                                self.mouse.handle_click_and_drag(landmarks[4], landmarks[8], landmarks)
                            elif target == "click_and_drag":
                                self.mouse.reset_scroll()
                                self.mouse.move_cursor(landmarks[8])
                                self.mouse.handle_click_and_drag(landmarks[4], landmarks[8], landmarks)
                            self.actions.emit_status(gesture_name, action_name, self.running, self.camera_status)
                        else:
                            # Reset continuous tracking components if not in mouse mode
                            self.mouse.reset_scroll()
                            self.mouse.release_mouse_safety()
                            self.actions.emit_status(gesture_name, action_name, self.running, self.camera_status)
                else:
                    # Reset tracking states if hands disappear
                    self.actions.reset_stabilizer()
                    self.mouse.reset_scroll()
                    self.mouse.release_mouse_safety()
                    self.actions.emit_status("None", "None", self.running, self.camera_status)
                    
                # Apply visual overlays to local frame (useful for debugging display or screenshot)
                self.tracker.draw_overlays(frame, results, gesture_name, action_name, fps)
                
                time.sleep(0.01)
        except Exception as e:
            has_error = True
            logger.error(f"GestureEngine runtime exception: {e}")
            gesture_state_manager.transition_to(GestureState.ERROR, str(e))
        finally:
            # Cleanup
            self.mouse.release_mouse_safety()
            if self.cap:
                self.cap.release()
                self.cap = None
            if not has_error:
                gesture_state_manager.transition_to(GestureState.STOPPED)

def start_gestures() -> bool:
    global ENGINE
    if gesture_state_manager.prevent_duplicate_instances():
        logger.warning("Gesture engine start ignored: duplicate instance detected.")
        return False
        
    if ENGINE is None:
        ENGINE = GestureEngine()
    return ENGINE.start()

def stop_gestures():
    global ENGINE
    if ENGINE is not None:
        ENGINE.stop()

def pause_gestures() -> bool:
    return gesture_state_manager.transition_to(GestureState.PAUSED)

def resume_gestures() -> bool:
    return gesture_state_manager.transition_to(GestureState.RUNNING)

def recover_gestures() -> bool:
    return gesture_state_manager.recover(start_gestures)
