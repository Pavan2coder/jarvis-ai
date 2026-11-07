"""Spotify / music command plugin.

Owns:
  Fallbacks — spotify playlist / launch / search (order 20)

`play_spotify` is also called directly by the system plugin's open_app handler
when the user asks to "open spotify" / "open music".
"""

import webbrowser

from backend.core import config
from backend.voice.audio_engine import speak


def play_spotify(command) -> bool:
    """Handle spotify/music/play/song/playlist commands. Returns True if handled."""
    if not any(w in command for w in ["spotify", "music", "play", "song", "playlist"]):
        return False

    # Check for playlist keywords
    for mood, url in config.SPOTIFY_PLAYLISTS.items():
        if mood in command and mood != "default":
            speak(f"Opening {mood} playlist on Spotify.")
            webbrowser.open(url)
            return True

    # Generic play command
    if "open spotify" in command or "launch spotify" in command:
        speak("Opening Spotify.")
        webbrowser.open(config.SPOTIFY_PLAYLISTS["default"])
        return True

    # Search for song/artist
    search_terms = (command
        .replace("play", "").replace("spotify", "")
        .replace("music", "").replace("song", "")
        .replace("search for", "").strip())

    if search_terms:
        speak(f"Searching Spotify for {search_terms}.")
        webbrowser.open(f"https://open.spotify.com/search/{search_terms.replace(' ', '%20')}")
        return True

    # Fallback
    speak("Opening Spotify.")
    webbrowser.open(config.SPOTIFY_PLAYLISTS["default"])
    return True


INTENTS = {}

FALLBACKS = [
    (20, play_spotify),
]
