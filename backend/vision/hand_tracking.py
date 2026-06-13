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
        """Converts frame to RGB and processes it through MediaPipe Hands."""
        if frame is None:
            return None
        # Convert color space for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return self.hands.process(rgb_frame)
        
    def get_fps(self) -> float:
        """Calculates live FPS based on duration between calls."""
        curr_time = time.time()
        fps = 1.0 / max(0.001, (curr_time - self.prev_time))
        self.prev_time = curr_time
        return fps
        
    def draw_overlays(self, frame, results, active_gesture: str, active_action: str, fps: float):
        """Draws tracking boxes, MediaPipe landmarks, active gesture, and system stats."""
        if frame is None:
            return
            
        h, w, _ = frame.shape
        
        # 1. Draw virtual mouse active tracking box bounds (25% to 75% width, 25% to 65% height)
        active_x_start, active_x_end = int(w * 0.25), int(w * 0.75)
        active_y_start, active_y_end = int(h * 0.25), int(h * 0.65)
        cv2.rectangle(frame, (active_x_start, active_y_start), (active_x_end, active_y_end), (58, 209, 255), 2)
        cv2.putText(frame, "ACTIVE AREA", (active_x_start + 5, active_y_start - 8), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (58, 209, 255), 1, cv2.LINE_AA)
                    
        # 2. Draw hand skeletons if landmarks are present
        if results and results.multi_hand_landmarks:
            for hand_lms in results.multi_hand_landmarks:
                self.mp_draw.draw_landmarks(
                    frame, 
                    hand_lms, 
                    self.mp_hands.HAND_CONNECTIONS,
                    self.mp_draw.DrawingSpec(color=(57, 255, 136), thickness=2, circle_radius=2),
                    self.mp_draw.DrawingSpec(color=(0, 240, 255), thickness=2, circle_radius=2)
                )
                
        # 3. Print FPS and Gesture HUD overlay text
        hud_bg_color = (18, 9, 2)
        # Background bars
        cv2.rectangle(frame, (8, 8), (220, 70), hud_bg_color, -1)
        cv2.rectangle(frame, (8, 8), (220, 70), (58, 209, 255), 1)
        
        cv2.putText(frame, f"FPS: {int(fps)}", (16, 26), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (39, 255, 136), 1, cv2.LINE_AA)
        cv2.putText(frame, f"GESTURE: {active_gesture.upper()}", (16, 44), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, f"ACTION: {active_action.upper()}", (16, 60), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (58, 209, 255), 1, cv2.LINE_AA)
