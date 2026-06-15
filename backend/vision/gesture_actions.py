import time
import threading
import pyautogui

class GestureActionsManager:
    def __init__(self):
        from backend.vision.gesture_debouncer import GestureDebouncer
        self.debouncer = GestureDebouncer()
        
        # States
        self.palm_start_time = None
        self.activated_this_palm = False
        
        # Debouncing current updates for WebSocket
        self.current_gesture = "None"
        self.current_action = "None"

    def stabilize_gesture_and_action(self, gesture: str, action: str, confidence: float = 1.0) -> tuple:
        """Delegates stabilization to the gesture debouncer."""
        return self.debouncer.add_frame(gesture, action, confidence)
        
    def reset_stabilizer(self):
        """Clears the stabilizer history queue to prevent lag on hand loss/re-acquisition."""
        self.debouncer.reset()
        
    def emit_status(self, gesture: str, action: str, engine_running: bool, camera_status: str):
        """Sends a WebSocket message back to the HUD on status/gesture changes."""
        if gesture == self.current_gesture and action == self.current_action:
            return  # Skip duplicate emissions
            
        self.current_gesture = gesture
        self.current_action = action
        
        try:
            from backend.websocket.events import dispatcher, JarvisEvent, JarvisEventType
            from backend.websocket.socket_manager import manager
            from backend.vision.profile_manager import profile_manager
            
            event = JarvisEvent(JarvisEventType.GESTURE_UPDATE, {
                "active": engine_running,
                "gesture": self.current_gesture,
                "action": self.current_action,
                "camera": camera_status,
                "profile": profile_manager.active_profile
            })
            dispatcher.emit_sync(event, loop=manager.loop)
        except Exception as e:
            # Silence logging to prevent audio frame lag
            pass
            
    def execute_discrete_actions(self, gesture: str, action: str, engine_running: bool, camera_status: str):
        """
        Dynamically executes actions based on the active gesture profile's mappings.
        """
        from backend.vision.profile_manager import profile_manager
        
        now = time.time()
        
        # Look up gesture mapping in active profile
        mapping = profile_manager.get_mapping_for_gesture(gesture)
        m_type = mapping.get("type", "none")
        target = mapping.get("target", "none")
        
        triggered = False
        
        # Check if the debouncer allows this gesture to trigger
        can_trigger = self.debouncer.can_trigger(gesture, target)
        
        if m_type == "system":
            if target == "activate_jarvis":
                # Wake up J.A.R.V.I.S waker hold logic (1.5s hold)
                if can_trigger:
                    if not self.palm_start_time:
                        self.palm_start_time = now
                    elif (now - self.palm_start_time > 1.5) and not self.activated_this_palm:
                        self.activated_this_palm = True
                        print(f"\n  🖐️  Gesture hold waker! Activating Jarvis...")
                        from backend.voice import audio_engine
                        if audio_engine.ENGINE is not None and not audio_engine.ENGINE.busy:
                            threading.Thread(target=audio_engine.ENGINE.activate, args=("gesture",), daemon=True).start()
                triggered = True
                
            elif target == "toggle_mute":
                if can_trigger:
                    print("\n  ✊ Mute gesture detected! Toggling audio...")
                    pyautogui.press('volumemute')
                    from backend.voice import audio_engine
                    audio_engine.speak("Toggling mute.")
                triggered = True
                
            elif target == "play_pause":
                if can_trigger:
                    print("\n  👍 Play/Pause gesture detected! Toggling media...")
                    pyautogui.press('playpause')
                    from backend.voice import audio_engine
                    audio_engine.speak("Media toggled.")
                triggered = True
                
        elif m_type == "key":
            if can_trigger:
                print(f"\n  🎹 Keystroke mapped: pressing '{target}' via gesture '{gesture}'")
                pyautogui.press(target)
            triggered = True
            
        # Reset waker hold status if not holding the waker gesture
        if m_type != "system" or target != "activate_jarvis":
            self.palm_start_time = None
            self.activated_this_palm = False
            
        # Emit WebSocket updates
        # If action mapped is none, we use the profile's mapped target name as HUD action
        hud_action = action if action != "None" else f"{m_type}:{target}".upper()
        self.emit_status(gesture, hud_action, engine_running, camera_status)
        
        return triggered
