"""
Shutdown Manager Module for Jarvis OS.
Coordinates the graceful cleanup and termination of hardware handles (camera, microphone),
active sockets, background queue workers, and threads to avoid resource leaks.

Architecture & Cleanup Workflow:
-------------------------------
1. Idempotency & Thread-Safety:
   `initiate_shutdown()` can be invoked from any thread (e.g. keypress interrupt, spoken voice command,
   WebSocket request). A reentrant lock guarantees only one shutdown sequence executes.

2. Priority-Ordered Hooks:
   Callbacks are registered with a priority. Lower numbers are executed first:
   - Priority 10: Stop Queue & Command Worker (Stop task ingestion and wait for in-progress operations).
   - Priority 20: Close WebSocket connections (Signal client UIs of offline state).
   - Priority 30: Terminate system engines (Release camera, release microphone streams).
   - Priority 40: State Persistence (Save conversation storage, configurations).
   - Priority 50: System exit.

3. Daemon Loop Monitoring:
   Background loops (e.g. diagnostics metrics collection) check `is_shutting_down()`
   to break loops cleanly.

Integration Examples:
---------------------
# To register a shutdown hook:
from core.shutdown_manager import shutdown_manager
shutdown_manager.register_handler("stop_mic", audio_engine.terminate, priority=30)

# To trigger shutdown:
shutdown_manager.initiate_shutdown(exit_code=0)
"""

import sys
import logging
import threading
from typing import Callable, List, Tuple

log = logging.getLogger("jarvis.shutdown_manager")

def safe_print(msg: str) -> None:
    """Prints a message to stdout, falling back to clean ASCII if encoding fails."""
    try:
        print(msg)
    except UnicodeEncodeError:
        try:
            clean_msg = msg.encode("ascii", "replace").decode("ascii")
            print(clean_msg)
        except Exception:
            pass

class ShutdownManager:
    """Manages cleanup handlers and coordinates graceful system termination."""
    
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._shutdown_event = threading.Event()
        # List of tuples: (priority, name, callback)
        self._handlers: List[Tuple[int, str, Callable[[], None]]] = []
        self._bypass_exit = False  # Used during testing to prevent sys.exit(0)
        
    def register_handler(self, name: str, callback: Callable[[], None], priority: int = 100) -> None:
        """Registers a cleanup callback with an execution priority."""
        with self._lock:
            # Check if name is already registered to prevent duplicates
            self._handlers = [h for h in self._handlers if h[1] != name]
            self._handlers.append((priority, name, callback))
            # Keep sorted by priority ascending
            self._handlers.sort(key=lambda x: x[0])
            log.debug(f"Registered shutdown handler '{name}' with priority {priority}")
            
    def is_shutting_down(self) -> bool:
        """Returns True if the shutdown process has been initiated."""
        return self._shutdown_event.is_set()
        
    @property
    def shutdown_event(self) -> threading.Event:
        """Returns the threading.Event used to signal shutdown."""
        return self._shutdown_event
        
    def initiate_shutdown(self, exit_code: int = 0) -> None:
        """Executes all registered cleanup hooks in priority order and exits the system."""
        # Double-check locking to guarantee thread-safe, single execution
        if self._shutdown_event.is_set():
            return
            
        with self._lock:
            if self._shutdown_event.is_set():
                return
                
            safe_print("\n  🛑  Initiating graceful shutdown workflow...")
            log.info("Shutdown sequence started (exit_code=%d)", exit_code)
            self._shutdown_event.set()
            
            # Execute all handlers sequentially
            for priority, name, callback in self._handlers:
                log.info(f"Executing cleanup [{priority}] '{name}'...")
                safe_print(f"  🔧  Cleaning up: {name}...")
                try:
                    callback()
                    log.info(f"Cleanup '{name}' completed successfully.")
                except Exception as e:
                    log.exception(f"Error executing cleanup handler '{name}': {e}")
                    safe_print(f"  ⚠️  Error cleaning up '{name}': {e}")
                    
            safe_print("  ✅  Jarvis OS shutdown complete.")
            log.info("Shutdown sequence finished.")
            
            if not self._bypass_exit:
                sys.exit(exit_code)

# Global Singleton Manager
shutdown_manager = ShutdownManager()
