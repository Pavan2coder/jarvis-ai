import threading
import time
import copy
from typing import Dict, Any, Callable, List, Optional, Tuple

class UIStateManager:
    """Thread-safe UI State Manager for Jarvis OS.
    
    Manages centralized HUD state, registers event-driven listeners, 
    and captures lock acquisition latency for diagnostics reporting.
    """
    
    def __init__(self):
        # Synchronization primitive
        self._lock = threading.RLock()
        
        # Centralized HUD state structure
        self._state: Dict[str, Any] = {
            "status": "idle",        # idle | listening | thinking | speaking
            "message": "Standing by...",
            "wake_source": "",
            "command": "",
            "response": "",
        }
        
        # Event subscription registry
        self._subscribers: List[Callable[[Dict[str, Any]], None]] = []
        
        # Diagnostics counters
        self._reads: int = 0
        self._writes: int = 0
        self._total_lock_wait_time_sec: float = 0.0
        self._last_updated_timestamp: float = 0.0

        # Register default WebSocket integration subscriber
        self.subscribe(self._default_websocket_notifier)

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]) -> Callable[[], None]:
        """Registers a listener callback that receives state snapshots on updates.
        
        Returns a callable function to unsubscribe.
        """
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)
            
        def unsubscribe():
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)
                    
        return unsubscribe

    def get_snapshot(self) -> Dict[str, Any]:
        """Returns a thread-safe snapshot (copy) of the current UI state."""
        start_time = time.perf_counter()
        with self._lock:
            wait_time = time.perf_counter() - start_time
            self._total_lock_wait_time_sec += wait_time
            self._reads += 1
            return copy.copy(self._state)

    def update_state(
        self,
        status: Optional[str] = None,
        message: Optional[str] = None,
        command: Optional[str] = None,
        response: Optional[str] = None,
        wake_source: Optional[str] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Thread-safely updates the state values.
        
        Arbitrary extra fields can be updated via kwargs.
        Triggers all subscribers with the new state snapshot.
        """
        start_time = time.perf_counter()
        subscribers_to_notify = []
        
        with self._lock:
            wait_time = time.perf_counter() - start_time
            self._total_lock_wait_time_sec += wait_time
            self._writes += 1
            self._last_updated_timestamp = time.time()
            
            # Apply standard updates, matching original ui_server.py behavior
            if status is not None:
                self._state["status"] = status
            if message is not None:
                # Keeps old message if new one is empty
                self._state["message"] = message or self._state["message"]
            if command is not None:
                self._state["command"] = command
            if response is not None:
                self._state["response"] = response
            if wake_source is not None:
                self._state["wake_source"] = wake_source
                
            # Apply extra fields
            for key, val in kwargs.items():
                self._state[key] = val
                
            # Create snapshot while holding the lock
            snapshot = copy.copy(self._state)
            
            # Fetch subscribers to notify while holding lock, but notify them outside the lock 
            # to avoid deadlocks in case callback calls state_manager methods.
            subscribers_to_notify = list(self._subscribers)
            
        # Notify subscribers outside lock
        for callback in subscribers_to_notify:
            try:
                callback(snapshot)
            except Exception as e:
                # Keep callbacks isolated so one failing listener won't abort updates
                import logging
                logging.getLogger("JARVIS").error(f"Error in UIState subscriber callback: {e}")
                
        return snapshot

    def get_diagnostics(self) -> Dict[str, Any]:
        """Gathers lock contention, read/write frequencies, and latency statistics."""
        with self._lock:
            total_ops = self._reads + self._writes
            avg_wait_ms = (
                (self._total_lock_wait_time_sec * 1000.0) / total_ops
                if total_ops > 0 else 0.0
            )
            return {
                "reads": self._reads,
                "writes": self._writes,
                "total_lock_wait_time_ms": self._total_lock_wait_time_sec * 1000.0,
                "avg_lock_wait_time_ms": avg_wait_ms,
                "last_updated_timestamp": self._last_updated_timestamp,
                "active_listeners": len(self._subscribers)
            }

    @staticmethod
    def _default_websocket_notifier(snapshot: Dict[str, Any]) -> None:
        """Internal subscriber that bridges state updates to the WebSocket event loop."""
        try:
            from backend.websocket.events import dispatcher, JarvisEvent, JarvisEventType
            from backend.websocket.socket_manager import manager

            status = snapshot.get("status")
            event_name = JarvisEventType.SYSTEM_UPDATE
            if status == "listening":
                event_name = JarvisEventType.AI_LISTENING
            elif status == "thinking":
                event_name = JarvisEventType.AI_THINKING
            elif status == "speaking":
                event_name = JarvisEventType.AI_SPEAKING

            event = JarvisEvent(event_name, data=snapshot)
            dispatcher.emit_sync(event, loop=manager.loop)
        except Exception:
            # Silence import/runtime errors if WebSocket subsystem is not initialized yet
            pass


# Global Singleton Instance
state_manager = UIStateManager()
