import math
import time
import pyautogui

class OneEuroFilter:
    def __init__(self, min_cutoff=0.05, beta=0.03, d_cutoff=1.0, freq=30.0):
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self.freq = float(freq)
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None

    def __call__(self, x, t=None):
        if t is None:
            t = time.time()
        
        # Reset if time gap is too large (e.g. tracking lost and recovered)
        if self.t_prev is None or (t - self.t_prev) > 1.0:
            self.x_prev = x
            self.t_prev = t
            self.dx_prev = 0.0
            return x

        dt = t - self.t_prev
        if dt <= 0:
            return self.x_prev

        self.freq = 1.0 / dt
        self.t_prev = t

        # Calculate derivative
        a_d = self._alpha(self.d_cutoff)
        dx = (x - self.x_prev) / dt
        dx_hat = a_d * dx + (1.0 - a_d) * self.dx_prev

        # Filter signal based on dynamic cutoff
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff)
        x_hat = a * x + (1.0 - a) * self.x_prev

        # Update tracking states
        self.x_prev = x_hat
        self.dx_prev = dx_hat

        return x_hat

    def _alpha(self, cutoff):
        te = 1.0 / self.freq
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / te)

class VirtualMouse:
    def __init__(self, smoothing: float = 6.0, min_cutoff: float = 0.05, beta: float = 0.04):
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
        self.prev_scroll_x = None
        
        # Initialize OneEuroFilters for smooth cursor tracking
        self.filter_x = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
        self.filter_y = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
        
        # Performance parameters
        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0.0
        
    def move_cursor(self, landmark):
        """
        Maps hand index landmark coordinates into scaled screen positions 
        and applies OneEuroFilter smoothing to prevent cursor jitters.
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
        
        # Apply OneEuroFilter dynamic smoothing filter
        curr_time = time.time()
        curr_x = self.filter_x(target_x, curr_time)
        curr_y = self.filter_y(target_y, curr_time)
        
        # Execute mouse move
        pyautogui.moveTo(int(curr_x), int(curr_y))
        
        # Save positions for next frame reference
        self.prev_x, self.prev_y = curr_x, curr_y
        
    def handle_click_and_drag(self, thumb_lm=None, index_lm=None, landmarks=None, is_clicking: bool = None):
        """
        Monitors pinch distance (thumb to index) if is_clicking is not specified.
        Otherwise, transitions smoothly into hold/drag state when is_clicking is True,
        and releases when is_clicking is False.
        """
        if is_clicking is not None:
            if is_clicking:
                if not self.mouse_down:
                    self.mouse_down = True
                    pyautogui.mouseDown()
            else:
                if self.mouse_down:
                    self.mouse_down = False
                    pyautogui.mouseUp()
            return

        if landmarks is not None:
            # Scale invariant pinch detection
            d_span = max(0.001, math.hypot(landmarks[5].x - landmarks[17].x, landmarks[5].y - landmarks[17].y))
            d_pinch = math.hypot(thumb_lm.x - index_lm.x, thumb_lm.y - index_lm.y)
            d_pinch_norm = d_pinch / d_span
            
            # Hysteresis thresholding to prevent click flickering
            pinch_threshold = 0.28
            release_threshold = 0.35
            
            if d_pinch_norm < pinch_threshold:
                if not self.mouse_down:
                    self.mouse_down = True
                    pyautogui.mouseDown()
            elif d_pinch_norm > release_threshold:
                if self.mouse_down:
                    self.mouse_down = False
                    pyautogui.mouseUp()
        else:
            # Static fallback thresholding
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
        """Tracks peace sign coordinates to control page scroll actions with dynamic speed."""
        # Calculate midpoints for both x and y to support 2D scrolling
        x_mid = (landmarks[8].x + landmarks[12].x) / 2.0
        y_mid = (landmarks[8].y + landmarks[12].y) / 2.0
        
        if self.prev_scroll_y is not None and self.prev_scroll_x is not None:
            dy = y_mid - self.prev_scroll_y
            dx = x_mid - self.prev_scroll_x
            
            # Vertical scroll
            if abs(dy) > 0.008:
                # Proportional scrolling: larger/faster moves scroll faster
                scroll_amount = -int(dy * 10000)
                pyautogui.scroll(scroll_amount)
                self.prev_scroll_y = y_mid
                
            # Horizontal scroll
            if abs(dx) > 0.008:
                scroll_amount = int(dx * 10000)
                try:
                    pyautogui.hscroll(scroll_amount)
                except Exception:
                    # Fallback if hscroll is unsupported on the system environment
                    pass
                self.prev_scroll_x = x_mid
        else:
            self.prev_scroll_y = y_mid
            self.prev_scroll_x = x_mid
            
    def reset_scroll(self):
        """Resets scroll state memory when scrolling is no longer active."""
        self.prev_scroll_y = None
        self.prev_scroll_x = None
        
    def release_mouse_safety(self):
        """Safety release for mouseDown state on shutdown/losses."""
        if self.mouse_down:
            self.mouse_down = False
            pyautogui.mouseUp()
