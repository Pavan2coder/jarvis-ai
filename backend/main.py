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
from core.shutdown_manager import shutdown_manager
from core.command_queue import COMMAND_QUEUE, CommandSource
from core.command_worker import CommandWorker

# Force UTF-8 console output so the emoji / box-drawing prints never crash on
# a Windows cp1252 codepage (and so logs survive being piped to a file).
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── Worker lifecycle callbacks ─────────────────────────────────────────────
# These run on the worker thread, never on the audio-capture thread.

def _on_command_start(item):
    """Gate the audio loop and update UI before executing a command."""
    if audio_engine.ENGINE is not None:
        audio_engine.ENGINE.busy = True
    ui_server.set_ui("thinking", message="Processing...", command=item.text)

def _on_command_end(item):
    """Release the audio loop and request an echo-flush after TTS finishes."""
    ui_server.set_ui("idle", message="Standing by...")
    if audio_engine.ENGINE is not None:
        # Signal the audio loop to flush the mic buffer on its next tick so
        # Jarvis's own TTS reply doesn't trigger a false wake-word match.
        audio_engine.ENGINE.flush_pending = True
        audio_engine.ENGINE.busy = False

def _on_command_error(item, exc):
    """Speak a brief error notice so the user isn't left in silence."""
    try:
        audio_engine.speak("Sorry, something went wrong with that command.")
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

        if COMMAND_QUEUE.is_shutting_down:
            return

        if not text:
            if audio_engine.ENGINE is None:
                print("  ⌨️  No microphone — type a command, e.g. 'what time is it'.")
            else:
                # plain ENTER → trigger a voice activation
                audio_engine.ENGINE.activate("manual")
            continue

        print(f"  ⌨️  You typed » {text}")
        if not COMMAND_QUEUE.put(text, CommandSource.CONSOLE):
            print("  ⚠️  Command queue is full or shutting down.")

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

    # Start the command worker — must be running before console_loop so that
    # typed commands work even when the mic is absent.
    worker = CommandWorker(
        handler=commands.handle_command,
        on_command_start=_on_command_start,
        on_command_end=_on_command_end,
        on_error=_on_command_error,
    )
    worker.start()

    # Register all graceful shutdown handlers
    def cleanup_queue_and_worker():
        COMMAND_QUEUE.shutdown()
        worker.stop(timeout=4.0)
        print(f"  📊  Queue stats: {COMMAND_QUEUE.stats}")
        print(f"  📊  Worker stats: {worker.stats}")

    def cleanup_audio_engine():
        if audio_engine.ENGINE is not None:
            audio_engine.ENGINE.terminate()

    def persist_states():
        from backend.assistant.session_memory import session_memory
        session_memory.clear()
        print("  💾  System state persisted.")

    from backend.websocket.socket_manager import manager as ws_manager
    from backend.system import gesture_engine

    shutdown_manager.register_handler("queue_and_worker", cleanup_queue_and_worker, priority=10)
    shutdown_manager.register_handler("websockets", ws_manager.close_all_sync, priority=20)
    shutdown_manager.register_handler("gesture_engine", gesture_engine.stop_gestures, priority=30)
    shutdown_manager.register_handler("audio_engine", cleanup_audio_engine, priority=30)
    shutdown_manager.register_handler("state_persistence", persist_states, priority=40)

    # Console typing always works
    threading.Thread(target=console_loop, daemon=True).start()

    # Run the mic engine (or idle if no mic); handle Ctrl+C for clean shutdown
    try:
        if audio_engine.ENGINE is not None:
            audio_engine.ENGINE.run()
        else:
            while not shutdown_manager.is_shutting_down():
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown_manager.initiate_shutdown(0)

if __name__ == "__main__":
    main()

