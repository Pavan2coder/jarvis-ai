import math
import pyautogui

class VirtualMouse:
    def __init__(self, smoothing: float = 6.0):
        self.screen_width, self.screen_height = pyautogui.size()
        self.prev_x, self.prev_y = 0.0, 0.0
        self.smoothing = smoothing
        
        # Click / Drag tracking
        self.mouse_down = False
        
        # Tracking bounding box coordinates (normalized)
        self.active_x_start = 0.25
        self.active_x_end = 0.75
        self.active_y_start = 0.25
        self.active_y_end = 0.65
        
        # Scroll tracking
        self.prev_scroll_y = None
        
        # Performance parameters
        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0.0
        
    def move_cursor(self, landmark):
        """
        Maps hand index landmark coordinates into scaled screen positions 
        and applies exponential smoothing to prevent cursor jitters.
        """
        ix, iy = landmark.x, landmark.y
        
        # Normalize target position relative to our active zone box
        cx = (ix - self.active_x_start) / (self.active_x_end - self.active_x_start)
        cy = (iy - self.active_y_start) / (self.active_y_end - self.active_y_start)
        cx = max(0.0, min(1.0, cx))
        cy = max(0.0, min(1.0, cy))
        
        # Scale to full screen size
        target_x = cx * self.screen_width
        target_y = cy * self.screen_height
        
        # Apply exponential smoothing filter
        curr_x = self.prev_x + (target_x - self.prev_x) / self.smoothing
        curr_y = self.prev_y + (target_y - self.prev_y) / self.smoothing
        
        # Execute mouse move
        pyautogui.moveTo(int(curr_x), int(curr_y))
        
        # Save positions for next frame reference
        self.prev_x, self.prev_y = curr_x, curr_y
        
    def handle_click_and_drag(self, thumb_lm, index_lm):
        """
        Monitors pinch distance (thumb to index). Transitions smoothly 
        into hold/drag state when pinched, and releases when open.
        """
        d_pinch = math.hypot(thumb_lm.x - index_lm.x, thumb_lm.y - index_lm.y)
        
        if d_pinch < 0.035:
            if not self.mouse_down:
                self.mouse_down = True
                pyautogui.mouseDown()
        elif d_pinch > 0.045:
            if self.mouse_down:
                self.mouse_down = False
                pyautogui.mouseUp()
                
    def handle_scrolling(self, landmarks):
        """Tracks peace sign coordinates to control page scroll actions."""
        # Middle finger landmark (12)
        y_mid = (landmarks[8].y + landmarks[12].y) / 2.0
        
        if self.prev_scroll_y is not None:
            dy = y_mid - self.prev_scroll_y
            if dy > 0.015:  # Hand moves down -> Scroll down
                pyautogui.scroll(-150)
                self.prev_scroll_y = y_mid
            elif dy < -0.015:  # Hand moves up -> Scroll up
                pyautogui.scroll(150)
                self.prev_scroll_y = y_mid
        else:
            self.prev_scroll_y = y_mid
            
    def reset_scroll(self):
        """Resets scroll state memory when scrolling is no longer active."""
        self.prev_scroll_y = None
        
    def release_mouse_safety(self):
        """Safety release for mouseDown state on shutdown/losses."""
        if self.mouse_down:
            self.mouse_down = False
            pyautogui.mouseUp()
