"""Spotify / music command plugin.

Owns:
  Fallbacks — media keys / spotify playlist / launch / play (order 20)

`play_spotify` is also called directly by the system plugin's open_app handler
when the user asks to "open spotify" / "open music".
"""

import os
import re
import time
import threading
import ctypes
import ctypes.wintypes as wt
import webbrowser

from backend.core import config
from backend.voice.audio_engine import speak

_MEDIA_KEYS = [  # (words, media key, reply)
    (("pause", "resume", "unpause"), "playpause", None),
    (("next song", "next track", "skip"), "nexttrack", "Skipping."),
    (("previous song", "previous track", "last song"), "prevtrack", "Going back."),
]

_FILLER = re.compile(r"\b(play|on spotify|in spotify|spotify|music|songs?|search for|some|me)\b")


def _spotify_window():
    """HWND of the Spotify desktop window, or None."""
    import psutil
    pids = {p.pid for p in psutil.process_iter(["name"])
            if (p.info["name"] or "").lower() == "spotify.exe"}
    found = []
    user32 = ctypes.windll.user32

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def _play_top_result(query) -> bool:
    """Search in the Spotify desktop app and press play on the top result.

    Spotify is a Chromium app, so its UI is exposed through Windows UI
    Automation: the 'Search results' grid's first row is the top result and
    its first button plays it. No screen coordinates, works at any window size.
    """
    import comtypes
    import comtypes.client
    comtypes.CoInitialize()
    comtypes.client.GetModule("UIAutomationCore.dll")
    from comtypes.gen import UIAutomationClient as U
    uia = comtypes.client.CreateObject(U.CUIAutomation, interface=U.IUIAutomation)

    def top_row():
        hwnd = _spotify_window()
        if not hwnd:
            return None
        grid = uia.ElementFromHandle(hwnd).FindFirst(
            U.TreeScope_Descendants, uia.CreatePropertyCondition(U.UIA_NamePropertyId, "Search results"))
        if not grid:
            return None
        return grid.FindFirst(U.TreeScope_Children, uia.CreatePropertyCondition(
            U.UIA_ControlTypePropertyId, U.UIA_DataItemControlTypeId))

    old = top_row()
    old_name = old.CurrentName if old else None
    os.startfile(f"spotify:search:{query}")

    # ponytail: polls up to 12s (cold app start); same query twice just waits it out.
    deadline = time.time() + 12
    row = None
    while time.time() < deadline:
        time.sleep(0.4)
        try:
            row = top_row()
        except Exception:
            row = None
        if row and (row.CurrentName != old_name or time.time() > deadline - 10):
            break
    if not row:
        return False

    buttons = row.FindAll(U.TreeScope_Descendants, uia.CreatePropertyCondition(
        U.UIA_ControlTypePropertyId, U.UIA_ButtonControlTypeId))
    for i in range(buttons.Length):
        b = buttons.GetElement(i)
        name = b.CurrentName or ""
        if name.startswith(("More options", "Add to", "Save")):
            continue
        b.GetCurrentPattern(U.UIA_InvokePatternId).QueryInterface(
            U.IUIAutomationInvokePattern).Invoke()
        return True
    return False


def play_spotify(command) -> bool:
    """Handle spotify/music/play/song/playlist commands. Returns True if handled."""
    for words, key, reply in _MEDIA_KEYS:
        if any(w in command for w in words):
            import pyautogui
            pyautogui.press(key)
            if reply:
                speak(reply)
            return True

    if not any(w in command for w in ["spotify", "music", "play", "song", "playlist"]):
        return False

    # Check for playlist keywords
    for mood, url in config.SPOTIFY_PLAYLISTS.items():
        if mood in command and mood != "default":
            speak(f"Opening {mood} playlist on Spotify.")
            webbrowser.open(url)
            return True

    query = re.sub(r"\s+", " ", _FILLER.sub(" ", command)).strip()
    if not query or "open spotify" in command or "launch spotify" in command:
        speak("Opening Spotify.")
        try:
            os.startfile("spotify:")
        except OSError:
            webbrowser.open(config.SPOTIFY_PLAYLISTS["default"])
        return True

    # Talk while Spotify loads the results instead of before.
    talker = threading.Thread(target=speak, args=(f"Playing {query} on Spotify.",))
    talker.start()
    try:
        played = _play_top_result(query)
    except Exception as e:
        print(f"  ⚠️  Spotify autoplay failed: {e}")
        played = False
    talker.join()
    if played:
        return True
    # No desktop app / UI changed: fall back to showing results in the browser.
    webbrowser.open(f"https://open.spotify.com/search/{query.replace(' ', '%20')}")
    return True


INTENTS = {}

FALLBACKS = [
    (20, play_spotify),
]
