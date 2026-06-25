"""
GestureEngine — VisionManager-subscriber gesture processor.

Removed from legacy implementation:
  - cv2.VideoCapture ownership (self.cap)
  - _run_loop capture thread
  - Manual frame flip (handled by SubscriberConfig flip_horizontal=True)
  - draw_overlays calls (no display consumer — dead CPU at 30 fps)

Frame flow
──────────
  VisionManager._capture_loop
      │  SubscriberConfig(fps_limit=30, flip_horizontal=True)
      ▼
  GestureEngine._on_frame(flipped_frame)    ← VisionManager subscriber worker thread
      ├─ HandTracker.process_frame()
      ├─ classify_gesture()
      ├─ GestureActionsManager (stabilize + discrete actions)
      └─ VirtualMouse (continuous mouse mode)

Companion change pending
────────────────────────
  camera_ops.py fallback (lines 54-73) opens its own cv2.VideoCapture when
  gesture engine is not running. Post-refactor, VisionManager owns the device
  even when gesture is stopped. Update that fallback to:

      from backend.vision.vision_manager import get_latest_frame
      frame = get_latest_frame()

  so it pulls from VisionManager instead of racing for the device.
"""

import threading

from backend.core import config
from backend.vision.hand_tracking import HandTracker
from backend.vision.gesture_recognizer import classify_gesture
from backend.vision.gesture_actions import GestureActionsManager
from backend.vision.virtual_mouse import VirtualMouse
from backend.vision.profile_manager import profile_manager
from backend.vision.gesture_state import gesture_state_manager, GestureState
from backend.utils.logger import logger

ENGINE = None


class GestureEngine:
    def __init__(self):
        self.running = False
        self._latest_frame = None
        self._frame_lock = threading.Lock()

        self.tracker = HandTracker()
        self.mouse = VirtualMouse()
        self.actions = GestureActionsManager()

        self.camera_status = "Inactive"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> bool:
        if self.running:
            return True
        if gesture_state_manager.prevent_duplicate_instances():
            logger.warning("Duplicate gesture start attempt blocked.")
            return False

        gesture_state_manager.transition_to(GestureState.STARTING)

        from backend.vision.vision_manager import start_vision, subscribe, SubscriberConfig
        from backend.vision.frame_provider import CameraConfig

        cam_cfg = CameraConfig(source=getattr(config, "CAMERA_INDEX", 0))
        if not start_vision(cam_cfg):
            logger.error("GestureEngine: VisionManager failed to open camera.")
            gesture_state_manager.transition_to(
                GestureState.ERROR, "VisionManager failed to open camera."
            )
            return False

        self.running = True
        self.camera_status = "Active"
        self.actions.reset_stabilizer()

        subscribe(
            "gesture",
            self._on_frame,
            SubscriberConfig(fps_limit=30, flip_horizontal=True),
        )

        gesture_state_manager.transition_to(GestureState.RUNNING)
        self.actions.emit_status("None", "None", self.running, self.camera_status)
        print("  🎥  Gesture Control Engine started.")
        return True

    def stop(self):
        if not self.running:
            return

        self.running = False
        self.camera_status = "Inactive"

        from backend.vision.vision_manager import unsubscribe
        unsubscribe("gesture")

        with self._frame_lock:
            self._latest_frame = None

        self.mouse.release_mouse_safety()
        self.actions.reset_stabilizer()

        if gesture_state_manager.get_state() != GestureState.ERROR:
            gesture_state_manager.transition_to(GestureState.STOPPED)

        self.actions.emit_status("None", "None", self.running, self.camera_status)
        print("  🎥  Gesture Control Engine stopped.")

    # ------------------------------------------------------------------
    # Frame access (pull-style, for camera_ops)
    # ------------------------------------------------------------------

    def get_latest_frame(self):
        """Thread-safe getter for the latest pre-flipped frame (no overlays)."""
        if not self.running or self._latest_frame is None:
            return None
        with self._frame_lock:
            return self._latest_frame.copy()

    # ------------------------------------------------------------------
    # Subscriber callback
    # ------------------------------------------------------------------

    def _on_frame(self, frame):
        """
        Push callback invoked by VisionManager's subscriber worker thread.
        Frame arrives pre-flipped (mirror view) via SubscriberConfig.
        No draw_overlays — no display consumer exists for the overlaid frame.
        """
        if not self.running:
            return

        # VisionManager delivers a fresh array (result of cv2.flip or .copy),
        # so storing the reference is safe — no downstream mutation.
        with self._frame_lock:
            self._latest_frame = frame

        gesture_state_manager.increment_frame_count()

        if gesture_state_manager.get_state() == GestureState.PAUSED:
            return

        try:
            results = self.tracker.process_frame(frame)
            gesture_name, action_name = "None", "None"

            if results and results.multi_hand_landmarks:
                landmarks = results.multi_hand_landmarks[0].landmark

                confidence = 1.0
                if results.multi_handedness:
                    confidence = results.multi_handedness[0].classification[0].score

                if profile_manager.active_profile == "work":
                    gesture_name, action_name = self.mouse.process_advanced_gestures(landmarks)
                    self.actions.emit_status(
                        gesture_name, action_name, self.running, self.camera_status
                    )
                else:
                    raw_gesture, raw_action = classify_gesture(landmarks)
                    gesture_name, action_name = self.actions.stabilize_gesture_and_action(
                        raw_gesture, raw_action, confidence
                    )

                    triggered = self.actions.execute_discrete_actions(
                        gesture_name, action_name, self.running, self.camera_status
                    )

                    if triggered:
                        self.mouse.release_mouse_safety()
                    else:
                        mapping = profile_manager.get_mapping_for_gesture(gesture_name)
                        m_type = mapping.get("type", "none")
                        target = mapping.get("target", "none")

                        if m_type == "mouse":
                            if target == "scroll":
                                self.mouse.handle_scrolling(landmarks)
                            elif target in ("move_cursor", "laser_pointer", "click_and_drag"):
                                self.mouse.reset_scroll()
                                self.mouse.move_cursor(landmarks)
                                is_clicking = (target == "click_and_drag")
                                self.mouse.handle_click_and_drag(is_clicking=is_clicking)
                            self.actions.emit_status(
                                gesture_name, action_name, self.running, self.camera_status
                            )
                        else:
                            self.mouse.reset_scroll()
                            self.mouse.release_mouse_safety()
                            self.actions.emit_status(
                                gesture_name, action_name, self.running, self.camera_status
                            )
            else:
                # No hand detected: decay stabilizer, release mouse.
                gesture_name, action_name = self.actions.stabilize_gesture_and_action(
                    "None", "None", 1.0
                )
                self.actions.execute_discrete_actions(
                    gesture_name, action_name, self.running, self.camera_status
                )
                self.mouse.reset_scroll()
                self.mouse.release_mouse_safety()
                
                # Reset advanced virtual mouse tracking states
                self.mouse.scroll_prev_y = None
                self.mouse.vol_prev_y = None
                self.mouse.pinched = False
                self.mouse.pinky_up = False
                self.mouse.ring_up = False
                self.mouse.spread_since = None
                self.mouse.palm_hist.clear()

        except Exception as e:
            logger.error(f"GestureEngine frame processing error: {e}")
            gesture_state_manager.transition_to(GestureState.ERROR, str(e))
            self.mouse.release_mouse_safety()
            self.running = False
            # Cannot call unsubscribe() here — that joins our own worker thread (deadlock).
            # self.running = False gates all future calls. unsubscribe on next stop()/recover().


# ----------------------------------------------------------------------
# Module-level API
# ----------------------------------------------------------------------

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
