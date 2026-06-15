import time
import threading
from enum import Enum
from backend.utils.logger import logger

class GestureState(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"

class GestureStateManager:
    """
    A thread-safe state manager for the J.A.R.V.I.S gesture vision system.
    Enforces valid transitions, prevents duplicate starts, manages recovery,
    and publishes state updates via WebSocket events.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """Singleton pattern to ensure only a single instance controls gesture system state."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(GestureStateManager, cls).__new__(cls)
            return cls._instance

    def __init__(self):
        # Prevent double initialization in Singleton
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        
        self.state = GestureState.STOPPED
        self.last_error = None
        self.error_timestamp = None
        self.start_timestamp = None
        self.frames_processed = 0
        self.lock = threading.Lock()
        
        # Valid state transitions lookup dictionary
        self._valid_transitions = {
            GestureState.STOPPED: {GestureState.STARTING},
            GestureState.STARTING: {GestureState.RUNNING, GestureState.ERROR, GestureState.STOPPED},
            GestureState.RUNNING: {GestureState.PAUSED, GestureState.STOPPED, GestureState.ERROR},
            GestureState.PAUSED: {GestureState.RUNNING, GestureState.STOPPED, GestureState.ERROR},
            GestureState.ERROR: {GestureState.STARTING, GestureState.STOPPED}
        }

    def get_state(self) -> GestureState:
        """Returns the current state thread-safely."""
        with self.lock:
            return self.state

    def transition_to(self, target_state: GestureState, error_msg: str = None) -> bool:
        """
        Transition the manager to a new target state.
        Enforces valid state transition paths.
        
        Returns:
            bool: True if successful, False otherwise.
        """
        with self.lock:
            current = self.state
            
            # Validate state transition
            valid_targets = self._valid_transitions.get(current, set())
            if target_state not in valid_targets:
                logger.warning(
                    f"Invalid gesture state transition rejected: {current.value} -> {target_state.value}"
                )
                return False
                
            # Update state and metadata
            self.state = target_state
            
            if target_state == GestureState.STARTING:
                self.start_timestamp = time.time()
                self.frames_processed = 0
                self.last_error = None
                self.error_timestamp = None
            elif target_state == GestureState.ERROR:
                self.last_error = error_msg or "Unknown runtime error"
                self.error_timestamp = time.time()
            elif target_state == GestureState.STOPPED:
                self.start_timestamp = None
                
            logger.info(f"Gesture system state changed: {current.value} -> {target_state.value}")
            
            # Emit status change via WebSocket
            self._broadcast_state()
            return True

    def prevent_duplicate_instances(self) -> bool:
        """
        Validates if another instance is already starting or running.
        
        Returns:
            bool: True if duplicate detected (STARTING or RUNNING), False if safe to proceed.
        """
        state = self.get_state()
        return state in (GestureState.STARTING, GestureState.RUNNING)

    def recover(self, engine_starter_callback) -> bool:
        """
        Attempts automatic recovery from ERROR state by transitioning to STARTING
        and running the engine start callback.
        
        Returns:
            bool: True if recovery attempt initiated successfully, False otherwise.
        """
        with self.lock:
            if self.state != GestureState.ERROR:
                logger.warning("Recovery bypass: gesture system is not in ERROR state.")
                return False
                
        logger.info("Attempting automatic gesture system recovery...")
        
        # Transition to STARTING (valid transition from ERROR)
        if not self.transition_to(GestureState.STARTING):
            return False
            
        try:
            # Call engine start callback
            success = engine_starter_callback()
            if success:
                logger.info("Gesture system recovery started successfully.")
                return True
            else:
                self.transition_to(GestureState.ERROR, "Recovery start callback returned failure.")
                return False
        except Exception as e:
            error_msg = f"Recovery attempt failed: {str(e)}"
            logger.error(error_msg)
            self.transition_to(GestureState.ERROR, error_msg)
            return False

    def get_status_report(self) -> dict:
        """
        Returns a comprehensive status report of the gesture system.
        
        Returns:
            dict: Current state, uptime, processed frames, errors, and profiles.
        """
        with self.lock:
            uptime = 0.0
            if self.start_timestamp is not None:
                uptime = time.time() - self.start_timestamp
                
            return {
                "state": self.state.value,
                "uptime": round(uptime, 2),
                "frames_processed": self.frames_processed,
                "last_error": self.last_error,
                "error_timestamp": self.error_timestamp,
                "active_profile": self._get_active_profile_name()
            }

    def increment_frame_count(self):
        """Thread-safely increments the frames processed count."""
        with self.lock:
            self.frames_processed += 1

    def _get_active_profile_name(self) -> str:
        try:
            from backend.vision.profile_manager import profile_manager
            return profile_manager.active_profile
        except Exception:
            return "unknown"

    def _broadcast_state(self):
        """Sends a WebSocket event package back to HUD updating client states."""
        try:
            from backend.websocket.events import dispatcher, JarvisEvent, JarvisEventType
            from backend.websocket.socket_manager import manager
            
            report = self.get_status_report()
            
            event = JarvisEvent(JarvisEventType.GESTURE_UPDATE, {
                "state_changed": True,
                "status": report
            })
            dispatcher.emit_sync(event, loop=manager.loop)
        except Exception:
            pass

    def reset(self):
        """Resets state to STOPPED and clears metrics."""
        with self.lock:
            self.state = GestureState.STOPPED
            self.last_error = None
            self.error_timestamp = None
            self.start_timestamp = None
            self.frames_processed = 0
            logger.info("GestureStateManager state reset to STOPPED.")

# Global state manager instance
gesture_state_manager = GestureStateManager()
