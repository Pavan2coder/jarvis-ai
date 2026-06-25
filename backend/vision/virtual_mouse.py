import ctypes
import time
import math
import cv2
import numpy as np
import pyautogui

# ── Windows API ───────────────────────────────────────────────────────────────
try:
    user32 = ctypes.windll.user32
    IS_WINDOWS = True
except (AttributeError, OSError):
    IS_WINDOWS = False

# Multi-monitor: virtual desktop spans all screens
if IS_WINDOWS:
    VIRT_X = user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
    VIRT_Y = user32.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN
    VIRT_W = user32.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
    VIRT_H = user32.GetSystemMetrics(79)   # SM_CYVIRTUALSCREEN
else:
    VIRT_X, VIRT_Y = 0, 0
    try:
        VIRT_W, VIRT_H = pyautogui.size()
    except Exception:
        VIRT_W, VIRT_H = 1920, 1080

M_MOVE  = 0x0001
M_ABS  = 0x8000
M_VIRT = 0x4000
M_LD    = 0x0002
M_LU   = 0x0004
M_RD    = 0x0008
M_RU   = 0x0010
M_MD    = 0x0020
M_MU   = 0x0040
M_WHEEL = 0x0800
KEYUP   = 0x0002

def _me(flags, x=0, y=0, d=0):
    if IS_WINDOWS:
        user32.mouse_event(flags, x, y, d, 0)
    else:
        # Fallback to pyautogui on non-Windows (for safety/compatibility)
        if flags & M_LD:
            pyautogui.mouseDown(button='left')
        if flags & M_LU:
            pyautogui.mouseUp(button='left')
        if flags & M_RD:
            pyautogui.mouseDown(button='right')
        if flags & M_RU:
            pyautogui.mouseUp(button='right')
        if flags & M_MD:
            pyautogui.mouseDown(button='middle')
        if flags & M_MU:
            pyautogui.mouseUp(button='middle')
        if flags & M_WHEEL:
            pyautogui.scroll(d)

def move(sx, sy):
    if IS_WINDOWS:
        nx = int((sx - VIRT_X) * 65535 / VIRT_W)
        ny = int((sy - VIRT_Y) * 65535 / VIRT_H)
        _me(M_MOVE | M_ABS | M_VIRT, nx, ny)
    else:
        pyautogui.moveTo(int(sx), int(sy))

def lclick():
    _me(M_LD)
    _me(M_LU)

def rclick():
    _me(M_RD)
    _me(M_RU)

def mclick():
    _me(M_MD)
    _me(M_MU)

def ldown():
    _me(M_LD)

def lup():
    _me(M_LU)

def scroll(d):
    _me(M_WHEEL, d=d)

def key_tap(*vks):
    if IS_WINDOWS:
        for k in vks:
            user32.keybd_event(k, 0, 0, 0)
        for k in reversed(vks):
            user32.keybd_event(k, 0, KEYUP, 0)
    else:
        # Fallback keypress
        key_names = []
        for k in vks:
            # Map common VK codes for compatibility
            if k == 0x12: key_names.append('alt')
            elif k == 0x25: key_names.append('left')
            elif k == 0x27: key_names.append('right')
            elif k == 0x09: key_names.append('tab')
            elif k == 0x5B: key_names.append('win')
            elif k == 0x44: key_names.append('d')
            elif k == 0xAF: key_names.append('volumeup')
            elif k == 0xAE: key_names.append('volumedown')
            elif k == 0x2C: key_names.append('printscreen')
        if key_names:
            pyautogui.hotkey(*key_names)

VK_ALT  = 0x12
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_TAB  = 0x09
VK_WIN  = 0x5B
VK_D     = 0x44
VK_VOLU = 0xAF
VK_VOLD = 0xAE
VK_SNAP  = 0x2C

# ── Kalman 2-D cursor smoother ────────────────────────────────────────────────
class Kalman2D:
    def __init__(self):
        self.kf = cv2.KalmanFilter(4, 2)
        self.kf.measurementMatrix   = np.array([[1,0,0,0],[0,1,0,0]], np.float32)
        self.kf.transitionMatrix    = np.array([[1,0,1,0],[0,1,0,1],
                                                [0,0,1,0],[0,0,0,1]], np.float32)
        self.kf.processNoiseCov     = np.eye(4, dtype=np.float32) * 0.03
        self.kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * 1.0
        self.kf.errorCovPost        = np.eye(4, dtype=np.float32)
        self._init = False

    def update(self, x, y):
        meas = np.array([[np.float32(x)], [np.float32(y)]])
        if not self._init:
            self.kf.statePre  = np.array([[x],[y],[0],[0]], np.float32)
            self.kf.statePost = np.array([[x],[y],[0],[0]], np.float32)
            self._init = True
        self.kf.predict()
        s = self.kf.correct(meas)
        return float(s[0]), float(s[1])

# Legacy OneEuroFilter kept for backward compatibility if referenced elsewhere
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
        a_d = self._alpha(self.d_cutoff)
        dx = (x - self.x_prev) / dt
        dx_hat = a_d * dx + (1.0 - a_d) * self.dx_prev
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff)
        x_hat = a * x + (1.0 - a) * self.x_prev
        self.x_prev = x_hat
        self.dx_prev = dx_hat
        return x_hat

    def _alpha(self, cutoff):
        te = 1.0 / self.freq
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / te)

class VirtualMouse:
    def __init__(self, smoothing: float = 6.0, min_cutoff: float = 0.05, beta: float = 0.04):
        # Multi-monitor compatibility
        self.screen_width, self.screen_height = VIRT_W, VIRT_H
        self.prev_x, self.prev_y = VIRT_X + VIRT_W/2.0, VIRT_Y + VIRT_H/2.0
        self.smoothing = smoothing
        
        # State tracking
        self.mouse_down = False
        
        # Tracking active zone boundaries
        self.active_x_start = 0.25
        self.active_x_end = 0.75
        self.active_y_start = 0.25
        self.active_y_end = 0.65
        
        # Scroll tracking
        self.prev_scroll_y = None
        self.prev_scroll_x = None
        
        # New Kalman Filter integration
        self.kf = Kalman2D()
        self.sx, self.sy = VIRT_X + VIRT_W/2.0, VIRT_Y + VIRT_H/2.0
        
        # New advanced gesture states
        self.last_l = 0.0
        self.last_r = 0.0
        self.last_vol = 0.0
        self.last_swipe = 0.0
        self.scroll_prev_y = None
        self.vol_prev_y = None
        self.pinched = False
        self.pinky_up = False
        self.ring_up = False
        self.spread_since = None
        self.palm_hist = []  # List of tuples: (px, py, timestamp)
        
        # Config constants from the uploaded file
        self.zone = 0.75
        self.deadzone = 5.0
        self.click_cd = 0.25
        self.dbl_win = 0.45
        self.vol_cd = 0.08
        self.vol_step = 0.012
        self.swipe_vel = 2.0
        self.swipe_cd = 1.0
        self.spread_hold = 1.2
        
        # Performance overrides
        if hasattr(pyautogui, 'FAILSAFE'):
            pyautogui.FAILSAFE = False
        if hasattr(pyautogui, 'PAUSE'):
            pyautogui.PAUSE = 0.0

    def fingers_up(self, lm):
        tips = [8, 12, 16, 20]
        pips = [6, 10, 14, 18]
        return [lm[t].y < lm[p].y for t, p in zip(tips, pips)]

    def palm_center(self, lm):
        """Average of wrist + 4 knuckle bases — much more stable than fingertip."""
        pts = [lm[i] for i in [0, 5, 9, 13, 17]]
        return sum(p.x for p in pts)/5, sum(p.y for p in pts)/5

    def hand_scale(self, lm):
        """Wrist-to-middle-MCP distance — used to normalise pinch threshold."""
        return np.hypot(lm[0].x - lm[9].x, lm[0].y - lm[9].y)

    def move_cursor(self, landmark_or_landmarks):
        """
        Maps hand landmark coordinates (either list of landmarks or single tip)
        into virtual screen coordinates and applies Kalman Filter smoothing with ballistics.
        """
        if isinstance(landmark_or_landmarks, list):
            px, py = self.palm_center(landmark_or_landmarks)
        else:
            px, py = landmark_or_landmarks.x, landmark_or_landmarks.y

        margin = (1.0 - self.zone) / 2.0
        tx = np.clip((px - margin) / self.zone, 0.0, 1.0) * VIRT_W + VIRT_X
        ty = np.clip((py - margin) / self.zone, 0.0, 1.0) * VIRT_H + VIRT_Y

        # pointer ballistics: amplify fast movements
        dist = np.hypot(tx - self.sx, ty - self.sy)
        accel = min(1.0 + dist / 300.0, 2.5)
        tx = self.sx + (tx - self.sx) * accel
        ty = self.sy + (ty - self.sy) * accel

        nx, ny = self.kf.update(tx, ty)
        if abs(nx - self.sx) > self.deadzone or abs(ny - self.sy) > self.deadzone:
            self.sx, self.sy = nx, ny
            move(self.sx, self.sy)
            self.prev_x, self.prev_y = self.sx, self.sy

    def handle_click_and_drag(self, thumb_lm=None, index_lm=None, landmarks=None, is_clicking: bool = None):
        """
        Windows ctypes-based click and drag implementation.
        """
        if is_clicking is not None:
            if is_clicking:
                if not self.mouse_down:
                    self.mouse_down = True
                    ldown()
            else:
                if self.mouse_down:
                    self.mouse_down = False
                    lup()
            return

        if landmarks is not None:
            d_span = max(0.001, np.hypot(landmarks[5].x - landmarks[17].x, landmarks[5].y - landmarks[17].y))
            d_pinch = np.hypot(thumb_lm.x - index_lm.x, thumb_lm.y - index_lm.y)
            d_pinch_norm = d_pinch / d_span
            
            pinch_threshold = 0.28
            release_threshold = 0.35
            
            if d_pinch_norm < pinch_threshold:
                if not self.mouse_down:
                    self.mouse_down = True
                    ldown()
            elif d_pinch_norm > release_threshold:
                if self.mouse_down:
                    self.mouse_down = False
                    lup()
        else:
            d_pinch = np.hypot(thumb_lm.x - index_lm.x, thumb_lm.y - index_lm.y)
            if d_pinch < 0.035:
                if not self.mouse_down:
                    self.mouse_down = True
                    ldown()
            elif d_pinch > 0.045:
                if self.mouse_down:
                    self.mouse_down = False
                    lup()

    def handle_scrolling(self, landmarks):
        """Tracks V-sign coordinates to control page scroll actions with ctypes."""
        if len(landmarks) > 12:
            x_mid = (landmarks[8].x + landmarks[12].x) / 2.0
            y_mid = (landmarks[8].y + landmarks[12].y) / 2.0
        else:
            # Fallback if only a single landmark is provided
            x_mid, y_mid = landmarks.x, landmarks.y
            
        if self.prev_scroll_y is not None:
            dy = y_mid - self.prev_scroll_y
            if abs(dy) > 0.005:
                scroll(int(-dy * 3000))
        self.prev_scroll_y = y_mid

    def reset_scroll(self):
        self.prev_scroll_y = None
        self.prev_scroll_x = None

    def release_mouse_safety(self):
        if self.mouse_down:
            self.mouse_down = False
            lup()

    # ── Advanced direct gesture processing loop ───────────────────────
    def process_advanced_gestures(self, landmarks) -> tuple:
        """
        Executes the direct gesture processing logic from the uploaded file.
        Uses hand shape transitions to trigger clicks, double clicks, scrolls,
        swiping, screenshots, and volume controls.
        
        Returns:
            tuple: (active_gesture_name, active_action_name)
        """
        now = time.time()
        fu = self.fingers_up(landmarks)
        px, py = self.palm_center(landmarks)
        scale = self.hand_scale(landmarks)
        
        # Adaptive pinch threshold
        dyn_pinch = float(np.clip(scale * 0.40, 0.03, 0.10))
        
        # Palm velocity history
        self.palm_hist.append((px, py, now))
        self.palm_hist = [(x, y, t) for x, y, t in self.palm_hist if now - t < 0.12]
        
        vel_x = vel_y = 0.0
        if len(self.palm_hist) >= 2:
            dt = self.palm_hist[-1][2] - self.palm_hist[0][2]
            if dt > 0:
                vel_x = (self.palm_hist[-1][0] - self.palm_hist[0][0]) / dt
                vel_y = (self.palm_hist[-1][1] - self.palm_hist[0][1]) / dt
                
        # Gesture flags
        pinch_d = np.hypot(landmarks[4].x - landmarks[8].x, landmarks[4].y - landmarks[8].y)
        is_pinched = pinch_d < dyn_pinch
        is_pinky = fu[3] and not fu[0] and not fu[1] and not fu[2]
        is_ring = fu[2] and not fu[0] and not fu[1] and not fu[3]
        is_volume = fu[2] and fu[3] and not fu[0] and not fu[1]
        is_spread = all(fu)
        
        lock_cursor = is_pinched or is_pinky or is_ring or is_volume
        label = "None"
        action = "None"
        
        # 1. Cursor movement
        if not lock_cursor:
            self.move_cursor(landmarks)
            label = "Index Point"
            action = "Hover/Move Mouse"
            
        # 2. Left Click / Double Click
        if is_pinched:
            if not self.pinched and (now - self.last_l) > self.click_cd:
                if (now - self.last_l) < self.dbl_win:
                    lclick()
                    lclick()
                    label = "Index Pinch"
                    action = "DOUBLE CLICK"
                else:
                    lclick()
                    label = "Index Pinch"
                    action = "LEFT CLICK"
                self.last_l = now
                self.scroll_prev_y = None
                if self.mouse_down:
                    lup()
                    self.mouse_down = False
            else:
                label = "Index Pinch"
                action = "Pinching"
                
        # 3. Right Click: Pinky tap (up -> down transition)
        elif self.pinky_up and not is_pinky and (now - self.last_r) > self.click_cd:
            rclick()
            self.last_r = now
            label = "Pinky Tap"
            action = "RIGHT CLICK"
            self.scroll_prev_y = None
            if self.mouse_down:
                lup()
                self.mouse_down = False
                
        # 4. Middle Click: Ring tap (up -> down transition)
        elif self.ring_up and not is_ring and (now - self.last_r) > self.click_cd:
            mclick()
            self.last_r = now
            label = "Ring Tap"
            action = "MIDDLE CLICK"
            self.scroll_prev_y = None
            if self.mouse_down:
                lup()
                self.mouse_down = False
                
        # 5. Continuous gestures (Volume, Scroll, Swipe, Drag)
        elif not is_pinched and not is_pinky and not is_ring:
            
            # Volume
            if is_volume:
                if self.vol_prev_y is not None and (now - self.last_vol) > self.vol_cd:
                    delta = self.vol_prev_y - py
                    if delta > self.vol_step:
                        key_tap(VK_VOLU)
                        self.last_vol = now
                        label = "Volume Gesture"
                        action = "VOL +"
                    elif delta < -self.vol_step:
                        key_tap(VK_VOLD)
                        self.last_vol = now
                        label = "Volume Gesture"
                        action = "VOL -"
                else:
                    label = "Volume Gesture"
                    action = "Adjusting Volume"
                self.vol_prev_y = py
                self.scroll_prev_y = None
                if self.mouse_down:
                    lup()
                    self.mouse_down = False
                    
            # Scroll (Index + Middle Up)
            elif fu[0] and fu[1] and not fu[2] and not fu[3]:
                cy = landmarks[8].y
                if self.scroll_prev_y is not None:
                    delta = self.scroll_prev_y - cy
                    if abs(delta) > 0.005:
                        scroll(int(delta * 3000))
                self.scroll_prev_y = cy
                self.vol_prev_y = None
                label = "Peace Sign"
                action = "Scroll"
                if self.mouse_down:
                    lup()
                    self.mouse_down = False
                    
            # Swipe / Navigation
            elif is_spread and (now - self.last_swipe) > self.swipe_cd:
                self.scroll_prev_y = None
                self.vol_prev_y = None
                if self.mouse_down:
                    lup()
                    self.mouse_down = False
                fired = False
                if abs(vel_x) > self.swipe_vel and abs(vel_x) > abs(vel_y):
                    if vel_x > 0:
                        key_tap(VK_ALT, VK_RIGHT)
                        label = "Open Palm"
                        action = ">> FORWARD"
                    else:
                        key_tap(VK_ALT, VK_LEFT)
                        label = "Open Palm"
                        action = "<< BACK"
                    fired = True
                elif abs(vel_y) > self.swipe_vel and abs(vel_y) > abs(vel_x):
                    if vel_y < 0:
                        key_tap(VK_ALT, VK_TAB)
                        label = "Open Palm"
                        action = "ALT + TAB"
                    else:
                        key_tap(VK_WIN, VK_D)
                        label = "Open Palm"
                        action = "SHOW DESKTOP"
                    fired = True
                if fired:
                    self.last_swipe = now
                    self.spread_since = None
                    
            # Drag (Fist / Closed Fist)
            elif not any(fu):
                if not self.mouse_down:
                    ldown()
                    self.mouse_down = True
                label = "Fist"
                action = "Click/Drag"
                self.scroll_prev_y = None
                self.vol_prev_y = None
                # Follow palm center for dragging
                self.move_cursor(landmarks)
                
            # Move / Hover fallback
            else:
                if self.mouse_down:
                    lup()
                    self.mouse_down = False
                self.scroll_prev_y = None
                self.vol_prev_y = None
                
        # 6. Screenshot (hold open palm for spread_hold duration)
        if is_spread and not (is_pinched or is_pinky or is_ring):
            if self.spread_since is None:
                self.spread_since = now
            held = now - self.spread_since
            if held >= self.spread_hold:
                key_tap(VK_WIN, VK_SNAP)
                label = "Open Palm"
                action = "SCREENSHOT!"
                self.spread_since = None
            elif label == "None" or not label:
                pct = int(held / self.spread_hold * 100)
                label = "Open Palm"
                action = f"SCREENSHOT {pct}%"
        elif not is_spread:
            self.spread_since = None
            
        # Update tap states
        self.pinched = is_pinched
        self.pinky_up = is_pinky
        self.ring_up = is_ring
        
        return label, action
