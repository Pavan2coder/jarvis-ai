"""
╚══════════════════════════════════════════════╝
║         J.A.R.V.I.S  —  Just A Rather Very Intelligent System ║
║                    Backend Orchestrator Entrypoint             ║
╚══════════════════════════════════════════════╝

RUN:
    python backend/main.py
    Then open http://localhost:5050 in your browser
"""

import sys
import os
import time
import threading
import webbrowser

# Add project root to sys.path to allow absolute imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.core import config
from backend.assistant import brain
from backend.api import ui_server
from backend.voice import audio_engine
from backend.assistant import commands

# Force UTF-8 console output so the emoji / box-drawing prints never crash on
# a Windows cp1252 codepage (and so logs survive being piped to a file).
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── console fallback: type commands even if the mic misbehaves ──
def console_loop():
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            return
        text = line.strip().lower()

        # No mic available → typed commands are the ONLY way in. Handle directly.
        if audio_engine.ENGINE is None:
            if not text:
                print("  ⌨️  No microphone — type a command, e.g. 'what time is it'.")
                continue
            print(f"  ⌨️  You typed » {text}")
            ui_server.set_ui("thinking", message="Processing...", command=text)
            commands.handle_command(text)
            ui_server.set_ui("idle", message="Standing by...")
            continue

        if not text:
            # plain ENTER → trigger a voice activation
            audio_engine.ENGINE.activate("manual")
            continue
        # typed command → handle directly (no mic needed); pause the mic loop
        audio_engine.ENGINE.busy = True
        try:
            print(f"  ⌨️  You typed » {text}")
            ui_server.set_ui("thinking", message="Processing...", command=text)
            commands.handle_command(text)
        finally:
            ui_server.set_ui("idle", message="Standing by...")
            audio_engine.ENGINE.busy = False

# ══════════════════════════════════════════════
# 🚀  BOOT
# ══════════════════════════════════════════════

def main():
    print("""
  ╔══════════════════════════════════════════════╗
  ║    J . A . R . V . I . S                     ║
  ║    Just A Rather Very Intelligent System     ║
  ╠══════════════════════════════════════════════╣
  ║  🗣️   Just speak     →  Runs the command      ║
  ║       (no "Jarvis" needed — wake-word-free)   ║
  ║  👏  Double clap    →  Wake Jarvis           ║
  ║  ⌨️   Press ENTER    →  Type a command        ║
  ║  🧠  Gemini AI brain + system control         ║
  ║  🌐  HUD launching automatically...          ║
  ╚══════════════════════════════════════════════╝
    """)

    # Start UI bridge server
    ui_thread = threading.Thread(target=ui_server.start_ui_server, daemon=True)
    ui_thread.start()
    print("  🌐  UI server running on http://localhost:5050")

    def launch_hud():
        time.sleep(1.2)
        print("  🖥️   Launching HUD at http://localhost:5050")
        webbrowser.open("http://localhost:5050")
    threading.Thread(target=launch_hud, daemon=True).start()

    # Check the Gemini AI brain
    ok, msg = brain.verify_gemini()
    print(f"  🧠  {msg}")

    # Build the single shared mic engine + calibrate to the room
    try:
        audio_engine.ENGINE = audio_engine.AudioEngine()
        audio_engine.ENGINE.calibrate()
    except Exception as e:
        print(f"  ⚠️  Could not open microphone: {e}")
        print("      You can still TYPE commands — press ENTER in this window.")
        audio_engine.ENGINE = None

    audio_engine.speak(f"Jarvis online. Good to see you, {config.YOUR_NAME}. All systems operational.")

    # Boot gesture control engine if configured
    if getattr(config, "GESTURES_ENABLED_ON_BOOT", False):
        try:
            from backend.system import gesture_engine
            gesture_engine.start_gestures()
        except Exception as e:
            print(f"  ⚠️  Could not start gesture engine on boot: {e}")

    # Console typing always works
    threading.Thread(target=console_loop, daemon=True).start()

    # Run the mic engine (or idle if no mic)
    if audio_engine.ENGINE is not None:
        audio_engine.ENGINE.run()
    else:
        while True:
            time.sleep(1)

if __name__ == "__main__":
    main()

