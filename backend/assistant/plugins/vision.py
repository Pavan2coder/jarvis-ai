"""Vision / gesture / camera command plugin.

Owns:
  Intents — camera_capture (photo), enable_gestures, disable_gestures
"""

import os

from backend.assistant.session_memory import session_memory
from backend.voice.audio_engine import speak


# ── Intent handlers (Layer A) ──────────────────────────────────────────────

def _camera_capture(command, entities):
    session_memory.set("current_task", "camera_capture")
    from backend.system import camera_ops
    speak("Taking a photo. Please look at the camera.")
    photo_path = camera_ops.capture_photo()
    if photo_path:
        filename = os.path.basename(photo_path)
        speak(f"Photo captured and saved to Desktop as {filename}.")
    else:
        speak("I was unable to capture a photo. Make sure your camera is connected.")


def _enable_gestures(command, entities):
    session_memory.set("current_task", "enable_gestures")
    from backend.vision.gesture_state import gesture_state_manager, GestureState
    current_state = gesture_state_manager.get_state()

    if current_state in (GestureState.RUNNING, GestureState.STARTING):
        speak("Gesture control is already active.")
    else:
        speak("Starting hand gesture control. Initializing camera.")
        from backend.system import gesture_engine
        gesture_engine.start_gestures()


def _disable_gestures(command, entities):
    session_memory.set("current_task", "disable_gestures")
    from backend.vision.gesture_state import gesture_state_manager, GestureState
    current_state = gesture_state_manager.get_state()

    if current_state == GestureState.STOPPED:
        speak("Gesture control is not running.")
    else:
        speak("Stopping hand gesture control. Releasing camera.")
        from backend.system import gesture_engine
        gesture_engine.stop_gestures()


def _enable_keyboard(command, entities):
    session_memory.set("current_task", "enable_keyboard")
    from backend.vision import virtual_keyboard
    if virtual_keyboard.is_running():
        speak("The gesture keyboard is already open.")
    else:
        speak("Opening the gesture keyboard. Point at a key and pinch to type.")
        if not virtual_keyboard.start_keyboard():
            speak("I couldn't start the gesture keyboard. Make sure your camera is connected.")


def _disable_keyboard(command, entities):
    session_memory.set("current_task", "disable_keyboard")
    from backend.vision import virtual_keyboard
    if not virtual_keyboard.is_running():
        speak("The gesture keyboard is not open.")
    else:
        speak("Closing the gesture keyboard.")
        virtual_keyboard.stop_keyboard()


INTENTS = {
    "camera_capture": _camera_capture,
    "enable_gestures": _enable_gestures,
    "disable_gestures": _disable_gestures,
    "enable_keyboard": _enable_keyboard,
    "disable_keyboard": _disable_keyboard,
}

FALLBACKS = []
