import time
import cv2
import mediapipe as mp

class HandTracker:
    def __init__(self, max_hands: int = 1, detection_con: float = 0.7, track_con: float = 0.7):
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            max_num_hands=max_hands,
            min_detection_confidence=detection_con,
            min_tracking_confidence=track_con
        )
        self.mp_draw = mp.solutions.drawing_utils
        self.prev_time = time.time()
        
    def process_frame(self, frame):
        """Converts frame to RGB, resizes for speed optimization, and processes it."""
        if frame is None:
            return None
            
        h, w, _ = frame.shape
        # Downscale to width 640 for faster MediaPipe processing (preserves aspect ratio)
        if w > 640:
            scale = 640.0 / w
            processing_frame = cv2.resize(frame, (640, int(h * scale)))
        else:
            processing_frame = frame
            
        # Convert color space for MediaPipe
        rgb_frame = cv2.cvtColor(processing_frame, cv2.COLOR_BGR2RGB)
        return self.hands.process(rgb_frame)
        
    def get_fps(self) -> float:
        """Calculates live FPS based on duration between calls."""
        curr_time = time.time()
        fps = 1.0 / max(0.001, (curr_time - self.prev_time))
        self.prev_time = curr_time
        return fps
        
    def draw_overlays(self, frame, results, active_gesture: str, active_action: str, fps: float):
        """Draws a premium holographic HUD, custom hand skeletons, and status indicators."""
        if frame is None:
            return
            
        h, w, _ = frame.shape
        
        # Smooth FPS calculation using EMA (exponential moving average)
        if not hasattr(self, "smooth_fps"):
            self.smooth_fps = fps
        else:
            self.smooth_fps = self.smooth_fps * 0.9 + fps * 0.1
            
        # Colors (BGR)
        cyan = (255, 209, 58)      # #3AD1FF
        neon_green = (136, 255, 57) # #39FF88
        hot_orange = (0, 128, 255)  # #FF8000
        gold = (0, 215, 255)       # #FFD700
        hud_bg = (18, 9, 2)        # Very dark blue/black
        
        # 1. Draw Active Area with styled corner brackets (Cyberpunk theme)
        active_x_start, active_x_end = int(w * 0.25), int(w * 0.75)
        active_y_start, active_y_end = int(h * 0.25), int(h * 0.65)
        
        # Draw faint connection box
        cv2.rectangle(frame, (active_x_start, active_y_start), (active_x_end, active_y_end), (100, 100, 100), 1, cv2.LINE_AA)
        
        # Draw corners
        length = 20
        # Top-Left
        cv2.line(frame, (active_x_start, active_y_start), (active_x_start + length, active_y_start), cyan, 2)
        cv2.line(frame, (active_x_start, active_y_start), (active_x_start, active_y_start + length), cyan, 2)
        # Top-Right
        cv2.line(frame, (active_x_end, active_y_start), (active_x_end - length, active_y_start), cyan, 2)
        cv2.line(frame, (active_x_end, active_y_start), (active_x_end, active_y_start + length), cyan, 2)
        # Bottom-Left
        cv2.line(frame, (active_x_start, active_y_end), (active_x_start + length, active_y_end), cyan, 2)
        cv2.line(frame, (active_x_start, active_y_end), (active_x_start, active_y_end - length), cyan, 2)
        # Bottom-Right
        cv2.line(frame, (active_x_end, active_y_end), (active_x_end - length, active_y_end), cyan, 2)
        cv2.line(frame, (active_x_end, active_y_end), (active_x_end, active_y_end - length), cyan, 2)
        
        cv2.putText(frame, "TRACKING BOUNDS", (active_x_start + 5, active_y_start - 8), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, cyan, 1, cv2.LINE_AA)
                    
        # 2. Draw Hand skeleton and state-driven virtual cursor
        if results and results.multi_hand_landmarks:
            for hand_lms in results.multi_hand_landmarks:
                # Custom drawings for cyberpunk skeleton look
                self.mp_draw.draw_landmarks(
                    frame, 
                    hand_lms, 
                    self.mp_hands.HAND_CONNECTIONS,
                    self.mp_draw.DrawingSpec(color=neon_green, thickness=2, circle_radius=2),
                    self.mp_draw.DrawingSpec(color=cyan, thickness=1, circle_radius=1)
                )
                
                # Render cursor at index finger tip (landmark 8)
                landmarks = hand_lms.landmark
                ix = int(landmarks[8].x * w)
                iy = int(landmarks[8].y * h)
                
                # Check active gesture and render custom visual indicators
                from backend.vision.profile_manager import profile_manager
                mapping = profile_manager.get_mapping_for_gesture("Index Point")
                is_laser = (mapping.get("type") == "mouse" and mapping.get("target") == "laser_pointer")
                
                if active_gesture == "Index Point":
                    if is_laser:
                        # Glowing red holographic laser pointer Core + Halo
                        red = (0, 0, 255)
                        cv2.circle(frame, (ix, iy), 6, (255, 255, 255), -1, cv2.LINE_AA)
                        cv2.circle(frame, (ix, iy), 12, red, -1, cv2.LINE_AA)
                        cv2.circle(frame, (ix, iy), 22, red, 2, cv2.LINE_AA)
                    else:
                        # Glowing neon blue dot + outer ring
                        cv2.circle(frame, (ix, iy), 6, cyan, -1, cv2.LINE_AA)
                        cv2.circle(frame, (ix, iy), 14, cyan, 1, cv2.LINE_AA)
                elif active_gesture == "Middle Pinch":
                    # Orange crosshair glow for click/drag state
                    cv2.circle(frame, (ix, iy), 8, hot_orange, -1, cv2.LINE_AA)
                    cv2.circle(frame, (ix, iy), 18, hot_orange, 2, cv2.LINE_AA)
                    cv2.line(frame, (ix - 25, iy), (ix + 25, iy), hot_orange, 1, cv2.LINE_AA)
                    cv2.line(frame, (ix, iy - 25), (ix, iy + 25), hot_orange, 1, cv2.LINE_AA)
                elif active_gesture == "Peace Sign" and active_action == "Scroll":
                    # Yellow scroll indicators
                    cv2.circle(frame, (ix, iy), 7, gold, -1, cv2.LINE_AA)
                    cv2.circle(frame, (ix, iy), 16, gold, 1, cv2.LINE_AA)
                    # Draw vertical indicator arrows
                    cv2.arrowedLine(frame, (ix, iy - 10), (ix, iy - 28), gold, 2, tipLength=0.3)
                    cv2.arrowedLine(frame, (ix, iy + 10), (ix, iy + 28), gold, 2, tipLength=0.3)
                    
        # 3. Premium Glassmorphic HUD overlay
        hud_w, hud_h = 240, 96
        hud_x, hud_y = 12, 12
        
        # Background alpha blend (semi-transparent glassmorphism look)
        overlay = frame.copy()
        cv2.rectangle(overlay, (hud_x, hud_y), (hud_x + hud_w, hud_y + hud_h), hud_bg, -1)
        cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)
        
        # Border
        cv2.rectangle(frame, (hud_x, hud_y), (hud_x + hud_w, hud_y + hud_h), cyan, 1, cv2.LINE_AA)
        
        # Content texts
        cv2.putText(frame, "J.A.R.V.I.S. VISION OS", (hud_x + 10, hud_y + 16), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, cyan, 1, cv2.LINE_AA)
        cv2.line(frame, (hud_x + 10, hud_y + 21), (hud_x + hud_w - 10, hud_y + 21), (100, 100, 100), 1)
        
        # Active profile mode
        from backend.vision.profile_manager import profile_manager
        profile_name = profile_manager.profiles.get(profile_manager.active_profile, {}).get("name", "Work Mode")
        cv2.putText(frame, f"MODE   : {profile_name.upper()}", (hud_x + 10, hud_y + 36), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, cyan, 1, cv2.LINE_AA)
        # FPS
        cv2.putText(frame, f"FPS    : {int(self.smooth_fps)}", (hud_x + 10, hud_y + 53), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, neon_green, 1, cv2.LINE_AA)
        # Gesture Name
        cv2.putText(frame, f"GESTURE: {active_gesture.upper()}", (hud_x + 10, hud_y + 70), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
        # Action Name
        cv2.putText(frame, f"ACTION : {active_action.upper()}", (hud_x + 10, hud_y + 86), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, gold, 1, cv2.LINE_AA)
