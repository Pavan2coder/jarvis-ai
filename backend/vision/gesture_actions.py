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
            
            event = JarvisEvent(JarvisEventType.GESTURE_UPDATE, {
                "active": engine_running,
                "gesture": self.current_gesture,
                "action": self.current_action,
                "camera": camera_status
            })
            dispatcher.emit_sync(event, loop=manager.loop)
        except Exception as e:
            # Silence logging to prevent audio frame lag
            pass
            
    def execute_discrete_actions(self, gesture: str, action: str, engine_running: bool, camera_status: str):
        """
        Executes non-mouse operations (e.g. system controls, wakers) 
        and updates states on matches.
        """
        now = time.time()
        
        # 1. Open Palm (🖐️) -> Wake up J.A.R.V.I.S
        if gesture == "Open Palm":
            if not self.palm_start_time:
                self.palm_start_time = now
            elif (now - self.palm_start_time > 1.5) and not self.activated_this_palm:
                self.activated_this_palm = True
                print("\n  🖐️  Open palm held! Activating Jarvis...")
                from backend.voice import audio_engine
                if audio_engine.ENGINE is not None and not audio_engine.ENGINE.busy:
                    threading.Thread(target=audio_engine.ENGINE.activate, args=("gesture",), daemon=True).start()
            self.emit_status(gesture, action, engine_running, camera_status)
            return True
            
        # Reset waker hold status if not palm
        self.palm_start_time = None
        self.activated_this_palm = False
        
        # 2. Fist (✊) -> Toggle Mute (2.5s cooldown)
        if gesture == "Fist":
            self.emit_status(gesture, action, engine_running, camera_status)
            if now - self.last_mute_time > 2.5:
                self.last_mute_time = now
                print("\n  ✊ Fist detected! Muting system audio...")
                pyautogui.press('volumemute')
                from backend.voice import audio_engine
                audio_engine.speak("Toggling mute.")
            return True
            
        # 3. Thumbs Up (👍) -> Play/Pause Spotify (2.5s cooldown)
        if gesture == "Thumbs Up":
            self.emit_status(gesture, action, engine_running, camera_status)
            if now - self.last_play_time > 2.5:
                self.last_play_time = now
                print("\n  👍 Thumbs Up detected! Play/Pause Spotify...")
                pyautogui.press('playpause')
                from backend.voice import audio_engine
                audio_engine.speak("Media toggled.")
            return True
            
        return False
