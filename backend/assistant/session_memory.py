import time
from typing import Any, Dict, Optional
from backend.core import config
from backend.utils.logger import logger

class SessionMemory:
    def __init__(self):
        """Initializes context tracking memory with a configurable TTL from settings."""
        self._context: Dict[str, Any] = {
            "last_opened_app": None,
            "last_command": None,
            "current_browser": None,
            "current_task": None,
        }
        self._last_updated: float = time.time()
        self.ttl = config.SESSION_TTL

    def set(self, key: str, value: Any):
        """Sets a context parameter and updates the active timestamp."""
        if key in self._context:
            self._context[key] = value
            self._last_updated = time.time()
            logger.info(f"SessionMemory updated: {key}='{value}'")

    def get(self, key: str) -> Optional[Any]:
        """Gets a context parameter if it has not expired."""
        if self.is_expired():
            self.clear()
            return None
        return self._context.get(key)

    def is_expired(self) -> bool:
        """Checks if the context TTL window has elapsed."""
        # If no context is set, it isn't considered expired but is empty
        if not any(value is not None for value in self._context.values()):
            return False
        return (time.time() - self._last_updated) > self.ttl

    def clear(self):
        """Resets all context parameters."""
        for key in self._context:
            self._context[key] = None
        self._last_updated = time.time()
        logger.info("SessionMemory context cleared/expired.")

    def get_all(self) -> Dict[str, Any]:
        """Returns all context parameters if not expired."""
        if self.is_expired():
            self.clear()
        return self._context.copy()

# Global Singleton Session Memory instance
session_memory = SessionMemory()
