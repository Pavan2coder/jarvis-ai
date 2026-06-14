import time
import threading
import pyautogui

class GestureActionsManager:
    def __init__(self):
        # Cooldowns and states
        self.last_mute_time = 0.0
        self.last_play_time = 0.0
        self.palm_start_time = None
        self.activated_this_palm = False
        
        # Debouncing current updates for WebSocket
        self.current_gesture = "None"
        self.current_action = "None"
        
        # Stabilizer history queue (stores (gesture, action) tuples)
        self.history = []
        self.history_len = 5

    def stabilize_gesture_and_action(self, gesture: str, action: str) -> tuple:
        """Appends gesture/action pair to history buffer and returns the majority voted pair."""
        self.history.append((gesture, action))
        if len(self.history) > self.history_len:
            self.history.pop(0)
            
        counts = {}
        for item in self.history:
            counts[item] = counts.get(item, 0) + 1
            
        return max(counts, key=counts.get)
        
    def reset_stabilizer(self):
        """Clears the stabilizer history queue to prevent lag on hand loss/re-acquisition."""
        self.history.clear()
        
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
        
        # Track previous gesture for transition edge-triggering
        if not hasattr(self, "last_gesture"):
            self.last_gesture = "None"
        if not hasattr(self, "last_gesture_time"):
            self.last_gesture_time = 0.0
            
        triggered = False
        
        if m_type == "system":
            if target == "activate_jarvis":
                # Wake up J.A.R.V.I.S waker hold logic (1.5s hold)
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
                if now - self.last_mute_time > 2.5:
                    self.last_mute_time = now
                    print("\n  ✊ Mute gesture detected! Toggling audio...")
                    pyautogui.press('volumemute')
                    from backend.voice import audio_engine
                    audio_engine.speak("Toggling mute.")
                triggered = True
                
            elif target == "play_pause":
                if now - self.last_play_time > 2.5:
                    self.last_play_time = now
                    print("\n  👍 Play/Pause gesture detected! Toggling media...")
                    pyautogui.press('playpause')
                    from backend.voice import audio_engine
                    audio_engine.speak("Media toggled.")
                triggered = True
                
        elif m_type == "key":
            # Keystroke trigger with transition edge-triggering + rate-limited auto-repeat
            is_new_gesture = (gesture != self.last_gesture)
            is_repeat_ready = (now - self.last_gesture_time > 0.8)
            
            if is_new_gesture or is_repeat_ready:
                self.last_gesture_time = now
                print(f"\n  🎹 Keystroke mapped: pressing '{target}' via gesture '{gesture}'")
                pyautogui.press(target)
            triggered = True
            
        # Reset waker hold status if not holding the waker gesture
        if m_type != "system" or target != "activate_jarvis":
            self.palm_start_time = None
            self.activated_this_palm = False
            
        # Save last gesture for next transition evaluation
        self.last_gesture = gesture
        
        # Emit WebSocket updates
        # If action mapped is none, we use the profile's mapped target name as HUD action
        hud_action = action if action != "None" else f"{m_type}:{target}".upper()
        self.emit_status(gesture, hud_action, engine_running, camera_status)
        
        return triggered
