import os
import json
from backend.utils.logger import logger

class GestureProfileManager:
    def __init__(self, config_path: str = None):
        if config_path is None:
            # Locate relative to backend config directory
            self.config_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.config_path = os.path.join(self.config_dir, "config", "gesture_profiles.json")
        else:
            self.config_path = config_path
            
        self.profiles = {}
        self.active_profile = "work"
        self.load_profiles()

    def load_profiles(self):
        """Loads gesture profiles from configuration file."""
        if not os.path.exists(self.config_path):
            # Write default template if config doesn't exist
            logger.warning(f"Gesture profiles config not found. Creating default at {self.config_path}")
            self._write_default_config()
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.profiles = data.get("profiles", {})
                self.active_profile = data.get("active_profile", "work")
                logger.info(f"Gesture profiles loaded. Active profile: {self.active_profile}")
        except Exception as e:
            logger.error(f"Error loading gesture profiles: {e}")
            self._write_default_config()

    def save_profiles(self):
        """Persists the profiles and the active profile preference to the JSON config file."""
        try:
            data = {
                "active_profile": self.active_profile,
                "profiles": self.profiles
            }
            # Ensure folder exists
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Gesture profiles saved successfully to {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save gesture profiles: {e}")
            return False

    def set_active_profile(self, profile_name: str) -> bool:
        """Switches the active profile and saves user preference."""
        if profile_name not in self.profiles:
            logger.warning(f"Profile '{profile_name}' not found. Available: {list(self.profiles.keys())}")
            return False
        
        self.active_profile = profile_name
        self.save_profiles()
        logger.info(f"Gesture profile switched to: {self.active_profile}")
        
        # Broadcast the change via WebSocket
        self.broadcast_profile_change()
        return True

    def get_active_profile_mappings(self) -> dict:
        """Returns the mapping dictionary for the active profile."""
        profile = self.profiles.get(self.active_profile, {})
        return profile.get("mappings", {})

    def get_mapping_for_gesture(self, gesture: str) -> dict:
        """Returns mapping for a specific gesture in the active profile."""
        mappings = self.get_active_profile_mappings()
        return mappings.get(gesture, {"type": "none", "target": "none"})

    def broadcast_profile_change(self):
        """Sends profile switch event to WebSocket HUD client."""
        try:
            from backend.websocket.events import dispatcher, JarvisEvent, JarvisEventType
            from backend.websocket.socket_manager import manager
            
            event = JarvisEvent(JarvisEventType.GESTURE_UPDATE, {
                "profile_changed": True,
                "active_profile": self.active_profile,
                "profile_details": {
                    "name": self.profiles[self.active_profile].get("name", ""),
                    "description": self.profiles[self.active_profile].get("description", "")
                }
            })
            dispatcher.emit_sync(event, loop=manager.loop)
        except Exception as e:
            pass

    def _write_default_config(self):
        """Generates default JSON profiles config if missing."""
        self.active_profile = "work"
        self.profiles = {
            "work": {
              "name": "Work Mode",
              "description": "Standard workspace cursor controls, scrolling, media shortcuts, and J.A.R.V.I.S waker.",
              "mappings": {
                "Index Point": {"type": "mouse", "target": "move_cursor"},
                "Middle Pinch": {"type": "mouse", "target": "click_and_drag"},
                "Peace Sign": {"type": "mouse", "target": "scroll"},
                "Open Palm": {"type": "system", "target": "activate_jarvis"},
                "Fist": {"type": "system", "target": "toggle_mute"},
                "Thumbs Up": {"type": "system", "target": "play_pause"}
              }
            },
            "gaming": {
              "name": "Gaming Mode",
              "description": "Key bindings mapped to gestures for in-game shortcuts and quick saves.",
              "mappings": {
                "Index Point": {"type": "mouse", "target": "move_cursor"},
                "Middle Pinch": {"type": "key", "target": "f"},
                "Thumbs Up": {"type": "key", "target": "space"},
                "Open Palm": {"type": "key", "target": "esc"},
                "Fist": {"type": "key", "target": "f5"},
                "Peace Sign": {"type": "key", "target": "tab"}
              }
            },
            "presentation": {
              "name": "Presentation Mode",
              "description": "Slide navigation and a virtual laser pointer overlay.",
              "mappings": {
                "Index Point": {"type": "mouse", "target": "laser_pointer"},
                "Middle Pinch": {"type": "key", "target": "f5"},
                "Open Palm": {"type": "key", "target": "right"},
                "Thumbs Up": {"type": "key", "target": "left"},
                "Fist": {"type": "key", "target": "b"},
                "Peace Sign": {"type": "mouse", "target": "scroll"}
              }
            }
        }
        self.save_profiles()

# Shared singleton instance
profile_manager = GestureProfileManager()
