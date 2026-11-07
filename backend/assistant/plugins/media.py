"""Media / entertainment command plugin.

Owns:
  Fallbacks — jokes (order 70)

Placeholder home for future media-playback commands (local music, video, etc.).
"""

import random

from backend.core import config
from backend.assistant.session_memory import session_memory
from backend.voice.audio_engine import speak


def _handle_joke(command) -> bool:
    if any(w in command for w in ["joke", "funny", "make me laugh"]):
        session_memory.set("current_task", "joke_query")
        speak(random.choice(config.jokes))
        return True
    return False


INTENTS = {}

FALLBACKS = [
    (70, _handle_joke),
]
