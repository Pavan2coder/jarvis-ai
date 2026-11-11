"""Browser / web command plugin.

Owns:
  Intents  — browser_automation (Playwright-driven search), search (context-aware
             webbrowser routing to YouTube / Spotify / Google)
  Fallbacks — folder opening (order 10), weather lookup (order 60)
"""

import os
import re
import difflib
import webbrowser

from backend.core import config
from backend.assistant.session_memory import session_memory
from backend.voice.audio_engine import speak
from backend.assistant.plugins.common import open_folder


# ── Intent handlers (Layer A) ──────────────────────────────────────────────

def _browser_automation(command, entities):
    session_memory.set("current_task", "browser_automation")
    action = entities.get("action")
    query = entities.get("query", "")
    if not query:
        speak("What would you like me to search for?")
        return
    from backend.automation import browser_control
    if action == "search_google":
        speak(f"Searching Google for {query}.")
        browser_control.automate_google_search(query)
    elif action == "search_youtube":
        speak(f"Opening YouTube and searching for {query}.")
        browser_control.automate_youtube_search(query)
    elif action == "search_github":
        speak(f"Opening GitHub and searching for {query}.")
        browser_control.automate_github_search(query)


def _search(command, entities):
    query = entities.get("query")
    if query:
        # Context-aware routing based on last opened app
        last_app = session_memory.get("last_opened_app")
        session_memory.set("current_task", f"search_{last_app or 'web'}")

        if last_app == "youtube" or "youtube" in command:
            speak(f"Searching YouTube for {query}.")
            webbrowser.open(f"https://www.youtube.com/results?search_query={query.replace(' ','+')}")
        elif last_app == "spotify" or "spotify" in command:
            speak(f"Searching Spotify for {query}.")
            webbrowser.open(f"https://open.spotify.com/search/{query.replace(' ', '%20')}")
        else:
            speak(f"Searching Google for {query}.")
            webbrowser.open(f"https://www.google.com/search?q={query.replace(' ','+')}")
    else:
        speak("What should I search for?")


# ── Fallback predicate handlers (Layer B) ──────────────────────────────────

_ITEM_FILLER = re.compile(
    r"\b(open|show|go to|launch|browse|navigate to|navigate|the|my|a|folder|directory|"
    r"file|called|named|on|in|from|inside|please|desktop|downloads|documents)\b")


def find_item(name):
    """Fuzzy-find a top-level file/folder by spoken name on the Desktop,
    then Documents, then Downloads. Returns its path or None."""
    entries = {}
    for key in ("desktop", "documents", "downloads"):
        base = config.FOLDERS.get(key)
        try:
            for e in os.listdir(base):
                stem = (e if os.path.isdir(os.path.join(base, e)) else os.path.splitext(e)[0]).lower()
                entries.setdefault(stem, os.path.join(base, e))
        except OSError:
            continue
    if name in entries:
        return entries[name]
    match = difflib.get_close_matches(name, list(entries), n=1, cutoff=0.7)
    return entries[match[0]] if match else None


def handle_folder_command(command) -> bool:
    # Only treat a folder-name mention as an "open folder" request when the
    # command actually asks to open/show it. Without this guard, unrelated
    # commands that merely contain a folder word (e.g. "minimise the desktop")
    # would wrongly open that folder. Match names as whole words too, so
    # "music" doesn't fire on "musical".
    open_ctx = any(v in command for v in ("open", "go to", "show", "launch", "browse", "navigate"))
    # "open the ERP folder on desktop" -> find "erp" before the generic
    # "desktop" match below swallows it.
    if open_ctx and re.search(r"\b(folder|directory|file|desktop|documents|downloads)\b", command):
        name = re.sub(r"\s+", " ", _ITEM_FILLER.sub(" ", command)).strip()
        path = find_item(name) if name and not os.path.isabs(name) else None
        if path:
            speak(f"Opening {os.path.basename(path)}.")
            open_folder(path)
            return True
    if open_ctx:
        for name, path in config.FOLDERS.items():
            if re.search(r"\b" + re.escape(name) + r"\b", command):
                if os.path.exists(path):
                    speak(f"Opening your {name} folder.")
                    open_folder(path)
                else:
                    speak(f"I couldn't find the {name} folder at {path}. Please update the path in the config.")
                return True

    # Custom path: "open folder C:/Users/..."
    if "open folder" in command or "open directory" in command:
        parts = command.replace("open folder", "").replace("open directory", "").strip()
        if parts:
            if os.path.exists(parts):
                speak(f"Opening {parts}.")
                open_folder(parts)
            else:
                speak(f"I couldn't find that folder path.")
        else:
            speak("Which folder would you like to open? Desktop, Downloads, Documents, Pictures, Music, or Videos?")
        return True

    return False


def _handle_weather(command) -> bool:
    if any(w in command for w in ["weather", "temperature", "forecast"]):
        session_memory.set("current_task", "weather_query")
        speak(f"Opening weather for {config.YOUR_CITY}.")
        webbrowser.open(f"https://www.google.com/search?q=weather+{config.YOUR_CITY.replace(' ','+')}")
        return True
    return False


INTENTS = {
    "browser_automation": _browser_automation,
    "search": _search,
}

FALLBACKS = [
    (10, handle_folder_command),
    (60, _handle_weather),
]
