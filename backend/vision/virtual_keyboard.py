"""
VirtualKeyboard — gesture-controlled on-screen keyboard.

Ported from Pavan2coder/Gesture-Controlled (mouse.py) and integrated into the
Jarvis vision stack:
  - Uses the shared VisionManager camera (pull-style get_latest_frame) instead of
    opening its own cv2.VideoCapture, so it never races the device.
  - Reuses the project's HandTracker (MediaPipe Hands).
  - Types into the focused window via pyautogui (pynput is not a dependency).
  - Plays a click sound via winsound (Windows) using assets/click.wav.

Interaction
───────────
  Index fingertip (landmark 8) = pointer. Hover over a key to highlight it.
  Pinch thumb tip (4) + index tip (8) together (< PINCH_PX) = press that key.
  A 0.5s cooldown prevents repeat presses. Press 'q' in the window to close.

A dedicated daemon thread owns the cv2 window + all imshow/waitKey calls so the
GUI stays on a single consistent thread.
"""

import os
import math
import time
import threading

import cv2

from backend.core import config
from backend.utils.logger import logger

# ── Layout (mirrors the source repo, sized for a 640×480 frame) ───────────────
KEYS = [
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
    ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
    ["A", "S", "D", "F", "G", "H", "J", "K", "L"],
    ["Z", "X", "C", "V", "B", "N", "M"],
    ["SPACE", "BACK"],
]
KEY_W, KEY_H = 60, 60
KEY_X0, KEY_Y0 = 30, 45
PINCH_PX = 38          # thumb–index distance (pixels) that counts as a "press"
CLICK_DELAY = 0.5      # seconds between presses
WINDOW_NAME = "J.A.R.V.I.S — Gesture Keyboard  (press q to close)"

_CLICK_WAV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "click.wav")

ENGINE = None


def _key_rect(row_idx, col_idx):
    """Pixel rectangle (x, y, w, h) for the key at [row_idx][col_idx]."""
    w = KEY_W * 4 if KEYS[row_idx][col_idx] in ("SPACE", "BACK") else KEY_W
    x = KEY_X0 + col_idx * (KEY_W + 8)
    y = KEY_Y0 + row_idx * (KEY_H + 8)
    return x, y, w, KEY_H


class VirtualKeyboard:
    def __init__(self):
        self.running = False
        self._thread = None
        self._last_click = 0.0
        self._tracker = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> bool:
        if self.running:
            return True

        # Shared camera owner — idempotent, no competing VideoCapture.
        from backend.vision.vision_manager import start_vision, get_latest_frame
        from backend.vision.frame_provider import CameraConfig

        cam_cfg = CameraConfig(source=getattr(config, "CAMERA_INDEX", 0))
        if not start_vision(cam_cfg):
            logger.error("VirtualKeyboard: VisionManager failed to open the camera.")
            return False

        from backend.vision.hand_tracking import HandTracker
        self._tracker = HandTracker()
        self._get_latest_frame = get_latest_frame

        self.running = True
        self._thread = threading.Thread(target=self._run_loop, name="virtual-keyboard", daemon=True)
        self._thread.start()
        print("  ⌨️   Gesture Keyboard started — point and pinch to type.")
        return True

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        print("  ⌨️   Gesture Keyboard stopped.")

    # ── sound + typing ────────────────────────────────────────────────────────

    def _play_click(self):
        try:
            import winsound
            winsound.PlaySound(_CLICK_WAV, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            pass  # non-Windows or missing asset — silent

    def _type(self, key):
        try:
            import pyautogui
            if key == "SPACE":
                pyautogui.press("space")
            elif key == "BACK":
                pyautogui.press("backspace")
            else:
                pyautogui.press(key.lower())
        except Exception as e:
            logger.error(f"VirtualKeyboard type error for '{key}': {e}")

    # ── drawing ───────────────────────────────────────────────────────────────

    def _draw_keyboard(self, img, hover=None):
        for i, row in enumerate(KEYS):
            for j, key in enumerate(row):
                x, y, w, h = _key_rect(i, j)
                active = hover == (i, j)
                if active:
                    cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), -1)
                    txt_color = (0, 0, 0)
                else:
                    cv2.rectangle(img, (x, y), (x + w, y + h), (255, 120, 0), 2)
                    txt_color = (255, 120, 0)
                cv2.putText(img, key, (x + 8, y + 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, txt_color, 2, cv2.LINE_AA)

    # ── main loop (own thread) ────────────────────────────────────────────────

    def _run_loop(self):
        logger.info("VirtualKeyboard display loop started")
        try:
            cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
            try:
                cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_TOPMOST, 1)
            except Exception:
                pass

            while self.running:
                raw = self._get_latest_frame()
                if raw is None:
                    time.sleep(0.02)
                    continue

                img = cv2.flip(raw, 1)  # mirror (selfie) view
                h, w, _ = img.shape

                results = self._tracker.process_frame(img)
                hover = None

                if results and results.multi_hand_landmarks:
                    lm = results.multi_hand_landmarks[0].landmark
                    ix, iy = int(lm[8].x * w), int(lm[8].y * h)   # index tip
                    tx, ty = int(lm[4].x * w), int(lm[4].y * h)   # thumb tip
                    distance = math.hypot(tx - ix, ty - iy)

                    cv2.circle(img, (ix, iy), 9, (0, 255, 0), cv2.FILLED)
                    cv2.circle(img, (ix, iy), 14, (0, 255, 0), 2)

                    # which key is the fingertip over?
                    for i, row in enumerate(KEYS):
                        for j, _key in enumerate(row):
                            x, y, kw, kh = _key_rect(i, j)
                            if x < ix < x + kw and y < iy < y + kh:
                                hover = (i, j)
                                if distance < PINCH_PX and (time.time() - self._last_click) > CLICK_DELAY:
                                    self._type(KEYS[i][j])
                                    self._last_click = time.time()
                                    self._play_click()

                self._draw_keyboard(img, hover)
                cv2.imshow(WINDOW_NAME, img)

                # 'q' or the window's X button closes the keyboard
                if (cv2.waitKey(1) & 0xFF) == ord("q"):
                    self.running = False
                    break
                try:
                    if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                        self.running = False
                        break
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"VirtualKeyboard loop error: {e}")
        finally:
            self.running = False
            try:
                cv2.destroyWindow(WINDOW_NAME)
                cv2.waitKey(1)
            except Exception:
                pass
            logger.info("VirtualKeyboard display loop ended")


# ── module-level API (mirrors gesture_engine) ─────────────────────────────────

def start_keyboard() -> bool:
    global ENGINE
    if ENGINE is None:
        ENGINE = VirtualKeyboard()
    return ENGINE.start()


def stop_keyboard():
    global ENGINE
    if ENGINE is not None:
        ENGINE.stop()


def is_running() -> bool:
    return ENGINE is not None and ENGINE.running
