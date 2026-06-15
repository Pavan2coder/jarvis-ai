import os
import json
from backend.utils.dotenv import load_dotenv
from backend.utils.logger import logger

class Settings:
    def __init__(self):
        # 1. Load variables from root .env file
        load_dotenv()
        
        self._config_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 2. Parse JSON configuration collections
        self.apps_data = self._load_json("apps.json")
        self.commands_data = self._load_json("commands.json")
        
        # 3. Environment variable triggers & overrides
        self.WAKE_WORD = os.environ.get("JARVIS_WAKE_WORD", "jarvis")
        self.CLAP_COOLDOWN = float(os.environ.get("JARVIS_CLAP_COOLDOWN", "0.20"))
        self.DOUBLE_CLAP_WINDOW = float(os.environ.get("JARVIS_DOUBLE_CLAP_WINDOW", "1.20"))
        self.YOUR_NAME = os.environ.get("JARVIS_YOUR_NAME", "Boss")
        self.YOUR_CITY = os.environ.get("JARVIS_YOUR_CITY", "Hyderabad")
        
        self.ALWAYS_LISTEN = os.environ.get("JARVIS_ALWAYS_LISTEN", "True").lower() == "true"
        self.REQUIRE_TRIGGER = os.environ.get("JARVIS_REQUIRE_TRIGGER", "True").lower() == "true"
        
        self.SAMPLE_RATE = int(os.environ.get("JARVIS_SAMPLE_RATE", "16000"))
        self.CHUNK = int(os.environ.get("JARVIS_CHUNK", "1024"))
        self.SPEECH_THRESHOLD = float(os.environ.get("JARVIS_SPEECH_THRESHOLD", "350"))
        self.CLAP_THRESHOLD = float(os.environ.get("JARVIS_CLAP_THRESHOLD", "3000"))
        
        self.GEMINI_MODEL = os.environ.get("JARVIS_GEMINI_MODEL", "gemini-2.5-flash")
        
        self.GESTURES_ENABLED_ON_BOOT = os.environ.get("JARVIS_GESTURES_ENABLED_ON_BOOT", "False").lower() == "true"
        self.CAMERA_INDEX = int(os.environ.get("JARVIS_CAMERA_INDEX", "0"))
        self.GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
        self.OLLAMA_URL = os.environ.get("JARVIS_OLLAMA_URL", "http://localhost:11434")
        self.OLLAMA_MODEL = os.environ.get("JARVIS_OLLAMA_MODEL", "llama3")
        self.SESSION_TTL = float(os.environ.get("JARVIS_SESSION_TTL", "300.0"))
        self.CLAP_SENSITIVITY = float(os.environ.get("JARVIS_CLAP_SENSITIVITY", "0.5"))

        # Gesture Debouncing & Cooldown configuration
        self.GESTURE_BUFFER_SIZE = int(os.environ.get("JARVIS_GESTURE_BUFFER_SIZE", "10"))
        self.GESTURE_STABILITY_THRESHOLD = int(os.environ.get("JARVIS_GESTURE_STABILITY_THRESHOLD", "7"))
        self.GESTURE_COOLDOWN_SECONDS = float(os.environ.get("JARVIS_GESTURE_COOLDOWN_SECONDS", "1.5"))
        self.GESTURE_CONFIDENCE_THRESHOLD = float(os.environ.get("JARVIS_GESTURE_CONFIDENCE_THRESHOLD", "0.65"))

        # WebSocket Reliability
        self.WS_HEARTBEAT_TIMEOUT = float(os.environ.get("JARVIS_WS_HEARTBEAT_TIMEOUT", "30.0"))
        
        # 4. Map loaded configuration structures
        self.APPS = self.apps_data.get("apps", {})
        self.CLOSE_PROCESSES = self.apps_data.get("close_processes", {})
        
        self.COMMAND_TRIGGERS = self.commands_data.get("command_triggers", [])
        self.WEB_TAB_WORDS = self.commands_data.get("web_tab_words", [])
        self.SPOTIFY_PLAYLISTS = self.commands_data.get("spotify_playlists", {})
        self.jokes = self.commands_data.get("jokes", [])
        
        # 5. Build dynamic system folders paths
        self.FOLDERS = {
            "desktop":   os.path.join(os.path.expanduser("~"), "Desktop"),
            "downloads": os.path.join(os.path.expanduser("~"), "Downloads"),
            "documents": os.path.join(os.path.expanduser("~"), "Documents"),
            "pictures":  os.path.join(os.path.expanduser("~"), "Pictures"),
            "music":     os.path.join(os.path.expanduser("~"), "Music"),
            "videos":    os.path.join(os.path.expanduser("~"), "Videos"),
            "projects":  os.path.join(os.path.expanduser("~"), "Projects"),
        }
        
        self.SYSTEM_PROMPT = (
            f"You are JARVIS, a witty, concise personal AI assistant for {self.YOUR_NAME}. "
            "Answer in 1-3 short spoken sentences. No markdown, no bullet points, no emojis "
            "— your reply is read aloud by a text-to-speech voice. Be helpful and direct."
        )
        
        logger.info("Configuration systems loaded successfully.")

    def _load_json(self, filename):
        path = os.path.join(self._config_dir, filename)
        if not os.path.exists(path):
            logger.warning(f"Configuration file {filename} does not exist at {path}.")
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading JSON configuration file {filename}: {e}")
            return {}

# Singleton instance
settings = Settings()
