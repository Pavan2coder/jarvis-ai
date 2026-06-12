import os
import sys
import datetime
import random
import subprocess
import webbrowser
import ctypes
import re

from backend.core import config
from backend.system import system_ops
from backend.assistant import brain
from backend.assistant.session_memory import session_memory
from backend.api import ui_server
from backend.voice.audio_engine import speak, listen
from backend.utils.logger import logger

# Pending shutdown/restart guard — must be confirmed before it fires
pending_power = {"action": None}

def open_folder(path):
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception as e:
        print(f"  ⚠️  Folder error: {e}")
        return False

def handle_folder_command(command):
    for name, path in config.FOLDERS.items():
        if name in command:
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

def handle_spotify_command(command):
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

def handle_close_command(command):
    """Handle 'close X' / 'kill X'. Returns True if it handled the command.
    Must run BEFORE the youtube/google branches, or 'close youtube' re-opens it."""
    if "close" not in command and "kill" not in command:
        return False

    target = (command.replace("close", "").replace("kill", "")
                     .replace("the", "").replace("app", "").replace("window", "")
                     .replace("please", "").strip())

    # "close" / "close this" with no real target → close the focused window's tab
    if not target or target in ("this", "it", "that"):
        if system_ops.close_active_browser_tab():
            speak("Closing the active tab.")
        else:
            speak("Install pyautogui so I can close tabs. Run pip install pyautogui.")
        return True

    # A website / browser tab (YouTube, Gmail, etc.) — close the focused tab.
    # ("browser" itself is a real process, handled below — exclude it here.)
    if any(w in target for w in config.WEB_TAB_WORDS) and "browser" not in target:
        if system_ops.close_active_browser_tab():
            speak(f"Closing the {target} tab. Make sure the browser is in focus.")
        else:
            speak("Install pyautogui so I can close browser tabs. Run pip install pyautogui.")
        return True

    # A real app → taskkill its process.
    procs = config.CLOSE_PROCESSES.get(target)
    if procs is None:
        for name, imgs in config.CLOSE_PROCESSES.items():
            if name in target or target in name:
                procs = imgs
                break
    if procs is None:
        # Last resort – guess process image name
        procs = [target.split()[0] + ".exe"]

    if system_ops.kill_processes(procs):
        speak(f"Closed {target}.")
    else:
        speak(f"{target} doesn't seem to be running.")
    return True

def handle_system_command(command):
    """Returns True if it handled a system/app command."""
    global pending_power

    # ── confirm / cancel a pending power action ──
    if pending_power["action"]:
        if any(w in command for w in ["yes", "confirm", "do it", "go ahead", "sure"]):
            act = pending_power["action"]
            pending_power = {"action": None}
            if act == "shutdown":
                speak("Confirmed. Shutting down in 15 seconds. Say cancel shutdown to stop.")
                subprocess.Popen(["shutdown", "/s", "/t", "15"])
            elif act == "restart":
                speak("Confirmed. Restarting in 15 seconds. Say cancel shutdown to stop.")
                subprocess.Popen(["shutdown", "/r", "/t", "15"])
            return True
        if any(w in command for w in ["no", "cancel", "stop", "don't", "abort"]):
            pending_power = {"action": None}
            speak("Cancelled. Staying on.")
            return True

    # ── cancel an already-scheduled shutdown ──
    if any(w in command for w in ["cancel shutdown", "abort shutdown", "stop shutdown"]):
        try:
            subprocess.Popen(["shutdown", "/a"])
            speak("Shutdown cancelled.")
        except Exception:
            speak("There was no shutdown to cancel.")
        return True

    # ── shutdown / restart (require confirmation) ──
    if any(w in command for w in ["shut down", "shutdown", "turn off computer", "turn off the computer"]):
        pending_power = {"action": "shutdown"}
        speak("Are you sure you want to shut down? Say yes to confirm or no to cancel.")
        return True
    if any(w in command for w in ["restart", "reboot"]):
        pending_power = {"action": "restart"}
        speak("Are you sure you want to restart? Say yes to confirm or no to cancel.")
        return True

    # ── lock / sleep ──
    if "lock" in command and ("pc" in command or "computer" in command or "screen" in command):
        speak("Locking your PC.")
        try: ctypes.windll.user32.LockWorkStation()
        except Exception: pass
        return True
    if any(w in command for w in ["sleep", "go to sleep", "suspend"]) and "computer" in command or "put the pc to sleep" in command:
        speak("Putting the computer to sleep.")
        try: subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        except Exception: pass
        return True

    # ── battery ──
    if "battery" in command:
        speak(system_ops.battery_status())
        return True

    # ── brightness ──
    if "brightness" in command:
        m = re.search(r"(\d{1,3})", command)
        if m:
            pct = int(m.group(1))
            speak(f"Setting brightness to {pct} percent." if system_ops.set_brightness_percent(pct)
                  else "Install screen-brightness-control for brightness. Run pip install screen-brightness-control.")
        elif any(w in command for w in ["up", "increase", "brighter", "max"]):
            speak("Brightness to max." if system_ops.set_brightness_percent(100) else "I can't control brightness on this display.")
        elif any(w in command for w in ["down", "decrease", "dim", "lower"]):
            speak("Dimming the screen." if system_ops.set_brightness_percent(30) else "I can't control brightness on this display.")
        else:
            speak("Tell me a brightness level, like set brightness to 50.")
        return True

    # ── set volume to a number ──
    if "volume" in command:
        m = re.search(r"(\d{1,3})", command)
        if m:
            pct = int(m.group(1))
            if system_ops.set_volume_percent(pct):
                speak(f"Volume set to {pct} percent.")
            else:
                speak("For exact volume levels install pycaw. Run pip install pycaw.")
            return True

    # ── gesture control ──
    if any(w in command for w in ["start gesture control", "enable gestures", "turn on camera", "enable gesture control"]) \
            or ("start" in command and "gesture" in command) \
            or ("enable" in command and "gesture" in command):
        from backend.system import gesture_engine
        speak("Starting hand gesture control. Initializing camera.")
        gesture_engine.start_gestures()
        return True

    if any(w in command for w in ["stop gesture control", "disable gestures", "turn off camera", "disable gesture control"]) \
            or ("stop" in command and "gesture" in command) \
            or ("disable" in command and "gesture" in command):
        from backend.system import gesture_engine
        speak("Stopping hand gesture control. Releasing camera.")
        gesture_engine.stop_gestures()
        return True


    # ── open an app ──
    if command.startswith("open ") or command.startswith("launch ") or command.startswith("start "):
        app = (command.replace("open", "", 1).replace("launch", "", 1)
                      .replace("start", "", 1).replace("the app", "").replace("app", "").strip())
        web_words = ("youtube", "google", "browser", "chrome browser")
        if app and app not in config.FOLDERS and not any(w in app for w in web_words):
            if system_ops.launch_app(app):
                speak(f"Opening {app}.")
            else:
                speak(f"I couldn't open {app}.")
            return True

    return False

def handle_command(command):
    if not command:
        speak("I didn't catch that. Call me again.")
        return

    # Normalize log output
    logger.info(f"Received user command: '{command}'")

    # Update session memory command history
    session_memory.set("last_command", command)

    # 1. Classify intent via NLP classifier
    from backend.assistant.intent_classifier import classify_intent
    result = classify_intent(command)
    intent = result["intent"]
    entities = result["entities"]

    logger.info(f"Parsed intent: '{intent}' (confidence: {result['confidence']}) with entities: {entities}")

    # 2. Dispatch based on Intent
    if intent == "browser_automation":
        session_memory.set("current_task", "browser_automation")
        action = entities.get("action")
        query = entities.get("query", "")
        if not query:
            speak("What would you like me to search for?")
            return
        from backend.system import browser_control
        if action == "search_google":
            speak(f"Searching Google for {query}.")
            browser_control.automate_google_search(query)
        elif action == "search_youtube":
            speak(f"Opening YouTube and searching for {query}.")
            browser_control.automate_youtube_search(query)
        elif action == "search_github":
            speak(f"Opening GitHub and searching for {query}.")
            browser_control.automate_github_search(query)
        return

    elif intent == "camera_capture":
        session_memory.set("current_task", "camera_capture")
        from backend.system import camera_ops
        speak("Taking a photo. Please look at the camera.")
        photo_path = camera_ops.capture_photo()
        if photo_path:
            filename = os.path.basename(photo_path)
            speak(f"Photo captured and saved to Desktop as {filename}.")
        else:
            speak("I was unable to capture a photo. Make sure your camera is connected.")
        return

    elif intent == "screenshot":
        session_memory.set("current_task", "screenshot_capture")
        try:
            import pyautogui
            fname = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            path  = os.path.join(os.path.expanduser("~"), "Desktop", fname)
            pyautogui.screenshot(path)
            speak(f"Screenshot saved to Desktop as {fname}.")
        except ImportError:
            speak("Install pyautogui first. Run: pip install pyautogui")
        return

    elif intent == "diagnostics":
        session_memory.set("current_task", "system_diagnostics")
        speak(system_ops.system_stats_report(command))
        return

    elif intent == "close_app":
        app_name = entities.get("app_name")
        if app_name:
            session_memory.set("current_task", f"closed_{app_name}")
            if session_memory.get("last_opened_app") == app_name:
                session_memory.set("last_opened_app", None)
                
            if any(w in app_name for w in config.WEB_TAB_WORDS) and "browser" not in app_name:
                if system_ops.close_active_browser_tab():
                    speak(f"Closing the {app_name} tab.")
                else:
                    speak("Install pyautogui so I can close browser tabs. Run pip install pyautogui.")
            else:
                procs = config.CLOSE_PROCESSES.get(app_name)
                if procs is None:
                    procs = [app_name + ".exe"]
                if system_ops.kill_processes(procs):
                    speak(f"Closed {app_name}.")
                else:
                    speak(f"{app_name} doesn't seem to be running.")
        else:
            speak("Which app would you like to close?")
        return

    elif intent == "open_app":
        app_name = entities.get("app_name")
        if app_name:
            # Set context variables
            session_memory.set("last_opened_app", app_name)
            session_memory.set("current_task", f"launched_{app_name}")
            if app_name in ["chrome", "edge", "firefox", "browser"]:
                session_memory.set("current_browser", app_name)
                
            # Check folder paths first
            if app_name in config.FOLDERS:
                path = config.FOLDERS[app_name]
                if os.path.exists(path):
                    speak(f"Opening your {app_name} folder.")
                    open_folder(path)
                return
            # Spotify playlist checks
            if app_name == "spotify" or app_name == "music":
                handle_spotify_command(command)
                return
            # Launch app
            if system_ops.launch_app(app_name):
                speak(f"Opening {app_name}.")
            else:
                speak(f"I couldn't open {app_name}.")
        else:
            speak("Which app would you like to open?")
        return

    elif intent == "search":
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
        return

    elif intent == "system_control":
        action = entities.get("action")
        val = entities.get("value")
        global pending_power
        
        session_memory.set("current_task", f"sys_ctrl_{action}")
        
        if action == "set_volume" and val is not None:
            if system_ops.set_volume_percent(val):
                speak(f"Volume set to {val} percent.")
            else:
                speak("Install pycaw for volume control. Run pip install pycaw.")
        elif action == "volume_up":
            speak("Turning it up.")
            try:
                import pyautogui
                for _ in range(5): pyautogui.press('volumeup')
            except: speak("Volume up failed.")
        elif action == "volume_down":
            speak("Turning it down.")
            try:
                import pyautogui
                for _ in range(5): pyautogui.press('volumedown')
            except: speak("Volume down failed.")
        elif action == "mute":
            speak("Muting.")
            try:
                import pyautogui
                pyautogui.press('volumemute')
            except: pass
            
        elif action == "set_brightness" and val is not None:
            speak(f"Setting brightness to {val} percent." if system_ops.set_brightness_percent(val)
                  else "I can't control brightness on this display.")
        elif action == "brightness_up":
            speak("Setting brightness to maximum." if system_ops.set_brightness_percent(100) else "I can't control brightness.")
        elif action == "brightness_down":
            speak("Dimming the screen." if system_ops.set_brightness_percent(30) else "I can't control brightness.")
            
        elif action == "shutdown":
            pending_power = {"action": "shutdown"}
            speak("Are you sure you want to shut down? Say yes to confirm.")
        elif action == "restart":
            pending_power = {"action": "restart"}
            speak("Are you sure you want to restart? Say yes to confirm.")
        elif action == "lock":
            speak("Locking your PC.")
            try: ctypes.windll.user32.LockWorkStation()
            except Exception: pass
        elif action == "sleep":
            speak("Putting the computer to sleep.")
            try: subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            except Exception: pass
            
        elif action == "enable_gestures":
            from backend.system import gesture_engine
            speak("Starting hand gesture control. Initializing camera.")
            gesture_engine.start_gestures()
        elif action == "disable_gestures":
            from backend.system import gesture_engine
            speak("Stopping hand gesture control. Releasing camera.")
            gesture_engine.stop_gestures()
        return

    elif intent == "greeting":
        session_memory.set("current_task", "greeting")
        speak(random.choice([
            f"Hello {config.YOUR_NAME}! All systems go. How can I help?",
            f"Hey {config.YOUR_NAME}! Ready and waiting.",
            f"Good to see you, {config.YOUR_NAME}. What do you need?",
        ]))
        return

    elif intent == "exit":
        speak(f"Goodbye {config.YOUR_NAME}. Jarvis signing off.")
        ui_server.set_ui("idle", message="Offline.")
        try:
            from backend.system import gesture_engine
            gesture_engine.stop_gestures()
        except Exception:
            pass
        os._exit(0)

    # 3. Fallbacks for existing helper functions
    if handle_folder_command(command):
        return
    if handle_spotify_command(command):
        return
    if handle_system_command(command):
        return

    # Custom checks for Time, Date, Weather, Jokes etc.
    if any(w in command for w in ["time", "clock"]):
        session_memory.set("current_task", "time_query")
        now = datetime.datetime.now().strftime("%I:%M %p")
        speak(f"It's {now}, {config.YOUR_NAME}.")
        return
    if any(w in command for w in ["date", "today", "day is it"]):
        session_memory.set("current_task", "date_query")
        today = datetime.datetime.now().strftime("%A, %B %d, %Y")
        speak(f"Today is {today}.")
        return
    if any(w in command for w in ["weather", "temperature", "forecast"]):
        session_memory.set("current_task", "weather_query")
        speak(f"Opening weather for {config.YOUR_CITY}.")
        webbrowser.open(f"https://www.google.com/search?q=weather+{config.YOUR_CITY.replace(' ','+')}")
        return
    if any(w in command for w in ["joke", "funny", "make me laugh"]):
        session_memory.set("current_task", "joke_query")
        speak(random.choice(config.jokes))
        return
    if "ip" in command:
        session_memory.set("current_task", "ip_query")
        import socket
        try:
            ip = socket.gethostbyname(socket.gethostname())
            speak(f"Your local IP is {ip}.")
        except: speak("Couldn't get your IP.")
        return
    if any(w in command for w in ["who are you", "what are you", "introduce"]):
        session_memory.set("current_task", "introduce")
        speak(f"I am Jarvis — Just A Rather Very Intelligent System. Personal AI assistant for {config.YOUR_NAME}.")
        return

    # ── Anything else → ask the Centralized LLM Router ──
    session_memory.set("current_task", "query_llm")
    ui_server.set_ui("thinking", message="Thinking...", command=command)
    from backend.assistant import llm_router
    answer = llm_router.ask_llm(command)
    speak(answer)
