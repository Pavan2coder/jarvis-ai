"""System / core command plugin.

Owns:
  Intents  — open_app, close_app, system_control, diagnostics, screenshot,
             workflow_automation, greeting, exit
  Fallbacks — system command (power/lock/sleep/battery/brightness/volume/open,
             order 30), time (40), date (50), ip (80), introduce (90)

Owns the `pending_power` confirmation guard used by both the system_control
intent and the system-command fallback.
"""

import os
import re
import random
import datetime
import ctypes
import subprocess
import threading

from core.shutdown_manager import shutdown_manager
from backend.core import config
from backend.system import system_ops
from backend.assistant.session_memory import session_memory
from backend.api import ui_server
from backend.voice.audio_engine import speak
from backend.assistant.plugins.common import open_folder

# Pending shutdown/restart guard — must be confirmed before it fires
pending_power = {"action": None}


# ── Intent handlers (Layer A) ──────────────────────────────────────────────

def _workflow_automation(command, entities):
    workflow_id = entities.get("workflow_id")
    if workflow_id:
        session_memory.set("current_task", f"workflow_{workflow_id}")
        from backend.automation.workflow_engine import workflow_engine
        workflow_engine.run_workflow_by_id(workflow_id)
    else:
        speak("I couldn't identify which workflow setup you requested.")


def _screenshot(command, entities):
    session_memory.set("current_task", "screenshot_capture")
    try:
        import pyautogui
        fname = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        # Use the resolved Desktop (honours OneDrive redirection); create it if
        # missing so pyautogui doesn't crash on a non-existent directory.
        save_dir = config.FOLDERS.get("desktop", os.path.join(os.path.expanduser("~"), "Desktop"))
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, fname)
        pyautogui.screenshot(path)
        speak(f"Screenshot saved to Desktop as {fname}.")
    except ImportError:
        speak("Install pyautogui first. Run: pip install pyautogui")


def _diagnostics(command, entities):
    session_memory.set("current_task", "system_diagnostics")
    speak(system_ops.system_stats_report(command))


def _close_app(command, entities):
    app_name = entities.get("app_name")
    if app_name:
        session_memory.set("current_task", f"closed_{app_name}")
        if session_memory.get("last_opened_app") == app_name:
            session_memory.set("last_opened_app", None)

        if any(w in app_name for w in config.WEB_TAB_WORDS) and "browser" not in app_name:
            if system_ops.close_active_browser_tab():
                # Avoid "the tab tab" when app_name is already "tab".
                label = app_name if "tab" in app_name else f"{app_name} tab"
                speak(f"Closing the {label}.")
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


def _open_app(command, entities):
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
            from backend.assistant.plugins import spotify
            spotify.play_spotify(command)
            return
        # Launch app
        if system_ops.launch_app(app_name):
            speak(f"Opening {app_name}.")
        else:
            speak(f"I couldn't open {app_name}.")
    else:
        speak("Which app would you like to open?")


def _system_control(command, entities):
    global pending_power
    action = entities.get("action")
    val = entities.get("value")

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


def _greeting(command, entities):
    session_memory.set("current_task", "greeting")
    speak(random.choice([
        f"Hello {config.YOUR_NAME}! All systems go. How can I help?",
        f"Hey {config.YOUR_NAME}! Ready and waiting.",
        f"Good to see you, {config.YOUR_NAME}. What do you need?",
    ]))


def _exit(command, entities):
    speak(f"Goodbye {config.YOUR_NAME}. Jarvis signing off.")
    ui_server.set_ui("idle", message="Offline.")
    # Trigger graceful shutdown asynchronously in a separate thread to prevent
    # self-joining deadlock (the command worker thread is joined during shutdown).
    threading.Thread(target=shutdown_manager.initiate_shutdown, args=(0,), daemon=True).start()


# ── Fallback predicate handlers (Layer B) ──────────────────────────────────

def handle_system_command(command) -> bool:
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


def _handle_time(command) -> bool:
    if re.search(r"\b(time|clock)\b", command):
        session_memory.set("current_task", "time_query")
        now = datetime.datetime.now().strftime("%I:%M %p")
        speak(f"It's {now}, {config.YOUR_NAME}.")
        return True
    return False


def _handle_date(command) -> bool:
    if re.search(r"\b(date|today)\b", command) or "day is it" in command:
        session_memory.set("current_task", "date_query")
        today = datetime.datetime.now().strftime("%A, %B %d, %Y")
        speak(f"Today is {today}.")
        return True
    return False


def _handle_ip(command) -> bool:
    if re.search(r"\bip\b", command):
        session_memory.set("current_task", "ip_query")
        import socket
        try:
            ip = socket.gethostbyname(socket.gethostname())
            speak(f"Your local IP is {ip}.")
        except: speak("Couldn't get your IP.")
        return True
    return False


def _handle_introduce(command) -> bool:
    if any(w in command for w in ["who are you", "what are you", "introduce"]):
        session_memory.set("current_task", "introduce")
        speak(f"I am Jarvis — Just A Rather Very Intelligent System. Personal AI assistant for {config.YOUR_NAME}.")
        return True
    return False


INTENTS = {
    "workflow_automation": _workflow_automation,
    "screenshot": _screenshot,
    "diagnostics": _diagnostics,
    "close_app": _close_app,
    "open_app": _open_app,
    "system_control": _system_control,
    "greeting": _greeting,
    "exit": _exit,
}

FALLBACKS = [
    (30, handle_system_command),
    (40, _handle_time),
    (50, _handle_date),
    (80, _handle_ip),
    (90, _handle_introduce),
]
