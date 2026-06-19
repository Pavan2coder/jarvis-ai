import time
import collections
import threading
from backend.core import config
from backend.utils.logger import logger

class GestureDebouncer:
    """
    A production-ready thread-safe gesture debouncing and cooldown system.
    
    Features:
    1. Rolling frame buffer (deque)
    2. Gesture stability check (majority voting with threshold)
    3. Cooldown timer per gesture/action
    4. Duplicate action prevention (edge-triggering on transitions)
    5. Confidence threshold filtering
    6. Configurable settings
    """
    def __init__(self, 
                 buffer_size: int = None, 
                 stability_threshold: int = None, 
                 default_cooldown: float = None, 
                 confidence_threshold: float = None):
        
        # Load configurable settings with defaults
        self.buffer_size = buffer_size if buffer_size is not None else getattr(config, "GESTURE_BUFFER_SIZE", 10)
        self.stability_threshold = stability_threshold if stability_threshold is not None else getattr(config, "GESTURE_STABILITY_THRESHOLD", 7)
        self.default_cooldown = default_cooldown if default_cooldown is not None else getattr(config, "GESTURE_COOLDOWN_SECONDS", 1.5)
        self.confidence_threshold = confidence_threshold if confidence_threshold is not None else getattr(config, "GESTURE_CONFIDENCE_THRESHOLD", 0.65)
        
        # Thread safety lock
        self.lock = threading.Lock()
        
        # Rolling frame buffer storing (gesture, action)
        self.buffer = collections.deque(maxlen=self.buffer_size)
        
        # Cooldown timestamps: maps gesture_name -> last_trigger_timestamp
        self.last_trigger_times = {}
        
        # Track last successfully triggered gesture to prevent duplicates during holds
        self.last_triggered_gesture = "None"
        
        # Set of continuous/hold-based gestures that bypass strict edge-triggering/cooldown checks
        self.continuous_gestures = {"Index Point", "Middle Pinch", "Peace Sign"}
        
        logger.info(
            f"GestureDebouncer initialized (buffer_size={self.buffer_size}, "
            f"stability_threshold={self.stability_threshold}, "
            f"default_cooldown={self.default_cooldown}s, "
            f"confidence_threshold={self.confidence_threshold})"
        )

    def add_frame(self, gesture: str, action: str, confidence: float) -> tuple:
        """
        Adds a raw gesture/action classification frame with its confidence score.
        Filters by confidence threshold and computes the current stable gesture.
        
        Returns:
            tuple: (stable_gesture, stable_action)
        """
        with self.lock:
            # 1. Confidence threshold check
            if confidence < self.confidence_threshold:
                # Treat low confidence as "None" to flush buffer
                gesture, action = "None", "None"
                
            # 2. Append to rolling buffer
            self.buffer.append((gesture, action))
            
            # 3. Stability check: compute majority vote
            counts = {}
            for g, a in self.buffer:
                counts[(g, a)] = counts.get((g, a), 0) + 1
                
            stable_gesture, stable_action = "None", "None"
            max_count = 0
            for (g, a), count in counts.items():
                if count > max_count:
                    max_count = count
                    stable_gesture, stable_action = g, a
                    
            # Check stability threshold
            if max_count < self.stability_threshold:
                stable_gesture, stable_action = "None", "None"
                
            # Reset transition tracking if no gesture is stable
            if stable_gesture == "None":
                self.last_triggered_gesture = "None"
                
            return stable_gesture, stable_action

    def can_trigger(self, gesture: str, action_target: str = None) -> bool:
        """
        Validates if the current stabilized gesture is allowed to trigger its action,
        enforcing cooldown timers and duplicate action prevention.
        
        Args:
            gesture: The stabilized gesture name.
            action_target: The action target/key mapping name.
            
        Returns:
            bool: True if allowed to trigger, False otherwise.
        """
        with self.lock:
            if gesture == "None":
                return False
                
            now = time.time()
            
            # Determine gesture behavioral characteristics
            is_continuous = (gesture in self.continuous_gestures or 
                             action_target in ("move_cursor", "laser_pointer", "click_and_drag", "scroll"))
            is_hold = (action_target == "activate_jarvis")
            
            # 1. Continuous and hold actions bypass standard edge-triggering/cooldown checks
            if is_continuous or is_hold:
                return True
                
            # 2. Enforce cooldown for discrete events
            last_time = self.last_trigger_times.get(gesture, 0.0)
            
            is_system = action_target in ("activate_jarvis", "toggle_mute", "play_pause", "move_cursor", "laser_pointer", "click_and_drag", "scroll")
            is_key = not is_system and action_target != "none" and action_target is not None
            
            # Key actions have their own auto-repeat rate of 0.8s, other discrete actions use the default cooldown
            cooldown = 0.8 if is_key else self.default_cooldown
            
            if (now - last_time) < cooldown:
                return False
                
            # 3. Duplicate action prevention (edge-triggering on transitions)
            is_transition = (gesture != self.last_triggered_gesture)
            
            # Keystroke mapping rate-limited auto-repeat support (e.g. key presses repeating every 0.8s)
            is_repeat_ready = False
            if not is_transition and is_key:
                # Allow keys to auto-repeat every 0.8 seconds (which is guaranteed to have passed if we reached here)
                is_repeat_ready = True
                    
            if is_transition or is_repeat_ready:
                self.last_trigger_times[gesture] = now
                self.last_triggered_gesture = gesture
                return True
                
            return False

    def reset(self):
        """Resets the debouncer buffer and cooldown memory."""
        with self.lock:
            self.buffer.clear()
            self.last_trigger_times.clear()
            self.last_triggered_gesture = "None"
            logger.info("GestureDebouncer history and timers reset.")
