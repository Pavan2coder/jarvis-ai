import threading
import time
import math
import cv2
import mediapipe as mp
import pyautogui

from backend.core import config


# Shared singleton instance
ENGINE = None

class GestureEngine:
    def __init__(self):
        self.running = False
        self.thread = None
        self.cap = None
        
        # MediaPipe initialization
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            max_num_hands=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        
        # Screen dimensions & cursor smoothing
        self.screen_width, self.screen_height = pyautogui.size()
        self.prev_x, self.prev_y = 0, 0
        self.smoothing = 6.0
        
        # Hysteresis mouse click / drag state
        self.mouse_down = False
        
        # Cooldowns for discrete gesture triggers
        self.last_mute_time = 0.0
        self.last_play_time = 0.0
        self.last_vscode_time = 0.0
        self.palm_start_time = None
        self.activated_this_palm = False
        
        # PyAutoGUI performance & fail-safe settings
        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0.0

    def start(self):
        if self.running:
            return True
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print("  🎥  Gesture Control Engine started.")
        return True

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
        print("  🎥  Gesture Control Engine stopped.")

    def _get_finger_states(self, landmarks):
        """Returns [thumb, index, middle, ring, pinky] booleans indicating if open."""
        states = [False] * 5
        
        # Fingers: open if tip y < pip y (remember y=0 is top, y=1 is bottom)
        states[1] = landmarks[8].y < landmarks[6].y
        states[2] = landmarks[12].y < landmarks[10].y
        states[3] = landmarks[16].y < landmarks[14].y
        states[4] = landmarks[20].y < landmarks[18].y
        
        # Thumb: compare distance between thumb tip (4) and index knuckle (5)
        # to the knuckle span width (5 to 17) to make it hand-agnostic.
        d_thumb_index = math.hypot(landmarks[4].x - landmarks[5].x, landmarks[4].y - landmarks[5].y)
        d_span = math.hypot(landmarks[5].x - landmarks[17].x, landmarks[5].y - landmarks[17].y)
        states[0] = d_thumb_index > d_span * 0.65
        
        return states

    def _run_loop(self):
        camera_idx = getattr(config, "CAMERA_INDEX", 0)
        self.cap = cv2.VideoCapture(camera_idx)
        if not self.cap.isOpened():
            print("  ⚠️  Could not open webcam for gesture control.")
            self.running = False
            return

        # Coordinate active box (normalized coordinates)
        active_x_start, active_x_end = 0.25, 0.75
        active_y_start, active_y_end = 0.25, 0.65
        
        prev_scroll_y = None
        
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
            
            # Flip horizontally to match mirror movement
            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape
            
            # Convert color space for MediaPipe
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb_frame)
            
            if results.multi_hand_landmarks:
                landmarks = results.multi_hand_landmarks[0].landmark
                states = self._get_finger_states(landmarks)
                
                # Check for Open Palm (🖐️) -> Pause tracking & Activate Jarvis
                if all(states):
                    if not self.palm_start_time:
                        self.palm_start_time = time.time()
                    elif (time.time() - self.palm_start_time > 1.5) and not self.activated_this_palm:
                        self.activated_this_palm = True
                        print("\n  🖐️  Open palm held! Activating Jarvis...")
                        from backend.voice import audio_engine
                        if audio_engine.ENGINE is not None and not audio_engine.ENGINE.busy:
                            threading.Thread(target=audio_engine.ENGINE.activate, args=("gesture",), daemon=True).start()
                    
                    # Pause mouse tracking in open palm
                    time.sleep(0.01)
                    continue
                else:
                    self.palm_start_time = None
                    self.activated_this_palm = False

                # Check for Fist (✊) -> Toggle Mute
                if not any(states):
                    now = time.time()
                    if now - self.last_mute_time > 2.5:
                        self.last_mute_time = now
                        print("\n  ✊ Fist detected! Muting system audio...")
                        pyautogui.press('volumemute')
                        from backend.voice import audio_engine
                        audio_engine.speak("Toggling mute.")
                    time.sleep(0.01)
                    continue

                # Check for Thumbs Up (👍) -> Play/Pause Music
                if states[0] and not any(states[1:]):
                    now = time.time()
                    if now - self.last_play_time > 2.5:
                        self.last_play_time = now
                        print("\n  👍 Thumbs Up detected! Play/Pause Spotify...")
                        pyautogui.press('playpause')
                        from backend.voice import audio_engine
                        audio_engine.speak("Media toggled.")
                    time.sleep(0.01)
                    continue

                # Check for Peace Sign (✌️) -> Scroll Mode (VS Code launch disabled)
                # Index and middle are open, other fingers are closed
                if states[1] and states[2] and not states[3] and not states[4]:
                    d_tips = math.hypot(landmarks[8].x - landmarks[12].x, landmarks[8].y - landmarks[12].y)
                    # If fingers are spread -> Do nothing (disabled VS Code launch)
                    if d_tips > 0.055:
                        time.sleep(0.01)
                        continue
                    
                    # If fingers are close -> Scroll Mode
                    else:
                        y_mid = (landmarks[8].y + landmarks[12].y) / 2.0
                        if prev_scroll_y is not None:
                            dy = y_mid - prev_scroll_y
                            if dy > 0.015:  # hand moving down
                                pyautogui.scroll(-150)
                                prev_scroll_y = y_mid
                            elif dy < -0.015:  # hand moving up
                                pyautogui.scroll(150)
                                prev_scroll_y = y_mid
                        else:
                            prev_scroll_y = y_mid
                        continue
                else:
                    prev_scroll_y = None

                # Virtual Mouse Mode
                # If index finger is open, move cursor
                if states[1]:
                    # Index tip landmark (8)
                    ix, iy = landmarks[8].x, landmarks[8].y
                    
                    # Map from active box to screen size
                    cx = (ix - active_x_start) / (active_x_end - active_x_start)
                    cy = (iy - active_y_start) / (active_y_end - active_y_start)
                    cx = max(0.0, min(1.0, cx))
                    cy = max(0.0, min(1.0, cy))
                    
                    target_x = int(cx * self.screen_width)
                    target_y = int(cy * self.screen_height)
                    
                    # Apply exponential smoothing
                    curr_x = self.prev_x + (target_x - self.prev_x) / self.smoothing
                    curr_y = self.prev_y + (target_y - self.prev_y) / self.smoothing
                    
                    pyautogui.moveTo(int(curr_x), int(curr_y))
                    self.prev_x, self.prev_y = curr_x, curr_y
                    
                    # Pinch to Click/Drag (Thumb tip 4 + Index tip 8)
                    d_pinch = math.hypot(landmarks[4].x - landmarks[8].x, landmarks[4].y - landmarks[8].y)
                    if d_pinch < 0.035:
                        if not self.mouse_down:
                            self.mouse_down = True
                            pyautogui.mouseDown()
                    elif d_pinch > 0.045:
                        if self.mouse_down:
                            self.mouse_down = False
                            pyautogui.mouseUp()
            
            # Optional sleep to reduce CPU load
            time.sleep(0.01)
            
        # Clean up camera
        if self.cap:
            self.cap.release()
            self.cap = None

def start_gestures():
    global ENGINE
    if ENGINE is None:
        ENGINE = GestureEngine()
    ENGINE.start()

def stop_gestures():
    global ENGINE
    if ENGINE is not None:
        ENGINE.stop()
