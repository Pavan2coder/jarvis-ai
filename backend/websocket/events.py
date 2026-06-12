import asyncio
import time
from enum import Enum
from typing import Dict, List, Callable, Any, Awaitable
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.websocket.socket_manager import manager
from backend.api.ui_server import ui_state
from backend.utils import logger

router = APIRouter()

# 1. Predefined Event Types
class JarvisEventType(str, Enum):
    AI_LISTENING = "AI_LISTENING"
    AI_THINKING = "AI_THINKING"
    AI_SPEAKING = "AI_SPEAKING"
    COMMAND_EXECUTED = "COMMAND_EXECUTED"
    SYSTEM_UPDATE = "SYSTEM_UPDATE"
    VOICE_DETECTED = "VOICE_DETECTED"

# 2. Event Payload Model
class JarvisEvent:
    def __init__(self, name: JarvisEventType, data: Any = None):
        self.name = name
        self.data = data or {}
        self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.name.value,
            "data": self.data,
            "timestamp": self.timestamp
        }

# 3. Async Event Registry & Dispatcher
class EventDispatcher:
    def __init__(self):
        # Maps event name to lists of async listener callback functions
        self._listeners: Dict[str, List[Callable[[JarvisEvent], Awaitable[None]]]] = {
            event.value: [] for event in JarvisEventType
        }
        # Wildcard list for listeners monitoring all event channels
        self._wildcard_listeners: List[Callable[[JarvisEvent], Awaitable[None]]] = []

    def register_listener(self, event_name: JarvisEventType, handler: Callable[[JarvisEvent], Awaitable[None]]):
        """Registers an async handler function for a specific event type."""
        name = event_name.value
        if name not in self._listeners:
            self._listeners[name] = []
        if handler not in self._listeners[name]:
            self._listeners[name].append(handler)
            logger.info(f"Registered listener for event: {name}")

    def register_wildcard_listener(self, handler: Callable[[JarvisEvent], Awaitable[None]]):
        """Registers a wildcard listener callback invoked on all events."""
        if handler not in self._wildcard_listeners:
            self._wildcard_listeners.append(handler)
            logger.info("Registered wildcard event listener.")

    def unregister_listener(self, event_name: JarvisEventType, handler: Callable[[JarvisEvent], Awaitable[None]]):
        """Removes a registered callback listener."""
        name = event_name.value
        if name in self._listeners and handler in self._listeners[name]:
            self._listeners[name].remove(handler)
            logger.info(f"Unregistered listener for event: {name}")

    def unregister_wildcard_listener(self, handler: Callable[[JarvisEvent], Awaitable[None]]):
        """Removes a registered wildcard listener callback."""
        if handler in self._wildcard_listeners:
            self._wildcard_listeners.remove(handler)
            logger.info("Unregistered wildcard event listener.")

    async def emit(self, event: JarvisEvent):
        """Asynchronously dispatches an event to all registered listeners."""
        tasks = []
        
        # Dispatch to specific event listeners
        handlers = self._listeners.get(event.name.value, [])
        for handler in handlers:
            tasks.append(self._safe_execute(handler, event))

        # Dispatch to wildcard listeners
        for wildcard_handler in self._wildcard_listeners:
            tasks.append(self._safe_execute(wildcard_handler, event))

        if tasks:
            await asyncio.gather(*tasks)

    def emit_sync(self, event: JarvisEvent, loop: asyncio.AbstractEventLoop = None):
        """Synchronously schedules the async dispatch of an event from non-async threads."""
        target_loop = loop or asyncio.get_event_loop()
        if target_loop and target_loop.is_running():
            asyncio.run_coroutine_threadsafe(self.emit(event), target_loop)
        else:
            try:
                asyncio.run(self.emit(event))
            except Exception as e:
                logger.error(f"Fallback direct event emit failed: {e}")

    async def _safe_execute(self, handler: Callable[[JarvisEvent], Awaitable[None]], event: JarvisEvent):
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"Error executing event handler {handler.__name__} for {event.name}: {e}")

# Global Event Dispatcher Singleton
dispatcher = EventDispatcher()

# 4. WebSocket Bridge (wildcard subscription broadcasting all events to active WS connections)
async def websocket_event_bridge(event: JarvisEvent):
    await manager.broadcast(event.to_dict())

dispatcher.register_wildcard_listener(websocket_event_bridge)

# 5. Router WebSocket Connection Endpoints
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket connection handler route."""
    await manager.connect(websocket)
    
    # Broadcast initial state wrap inside SYSTEM_UPDATE event
    initial_event = JarvisEvent(JarvisEventType.SYSTEM_UPDATE, data=ui_state)
    await manager.send_personal_message(initial_event.to_dict(), websocket)
    
    try:
        while True:
            data = await websocket.receive_json()
            logger.info(f"Received WebSocket data: {data}")
            
            # Allow clients to emit events back into the dispatch loop
            if isinstance(data, dict) and "event" in data:
                try:
                    event_type = JarvisEventType(data["event"])
                    client_event = JarvisEvent(event_type, data.get("data", {}))
                    await dispatcher.emit(client_event)
                except ValueError:
                    logger.warning(f"Client sent unrecognized event type: {data['event']}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        manager.disconnect(websocket)

"""
================================================================================
J.A.R.V.I.S OS - Event-Driven Architecture Examples & Integration Guide
================================================================================

1. Event Architecture:
   - Pub/Sub Pattern: Modules subscribe to EventTypes through the global `dispatcher`.
   - Event Emitter: Any synchronous or asynchronous thread can emit events.
   - WebSocket Bridge: All emitted events are automatically serialized and broadcast
     to connected WebSocket clients in real-time.

2. Event Emitter Example:
   -----------------------------------------------------------------------------
   from backend.websocket.events import dispatcher, JarvisEvent, JarvisEventType

   # Asynchronous Emit (from async functions):
   async def trigger_voice_start():
       event = JarvisEvent(JarvisEventType.VOICE_DETECTED, {"intensity": 0.85})
       await dispatcher.emit(event)

   # Synchronous Emit (from background blocking threads):
   def on_command_complete(command_text, status):
       event = JarvisEvent(JarvisEventType.COMMAND_EXECUTED, {
           "command": command_text, 
           "status": status
       })
       # Automatically schedules it safely in the FastAPI uvicorn event loop:
       from backend.websocket.socket_manager import manager
       dispatcher.emit_sync(event, loop=manager.loop)
   -----------------------------------------------------------------------------

3. Listener Example:
   -----------------------------------------------------------------------------
   from backend.websocket.events import dispatcher, JarvisEvent, JarvisEventType

   async def on_voice_detected(event: JarvisEvent):
       print(f"[Listener] Voice audio frame captured: {event.data}")

   # Register listener:
   dispatcher.register_listener(JarvisEventType.VOICE_DETECTED, on_voice_detected)
   -----------------------------------------------------------------------------

4. Integration Example (State Sync / UI Server integration):
   -----------------------------------------------------------------------------
   def set_ui(status, message="", command="", response="", wake_source=""):
       # Update status state...
       # Emit SYSTEM_UPDATE event:
       event = JarvisEvent(JarvisEventType.SYSTEM_UPDATE, data=ui_state)
       from backend.websocket.socket_manager import manager
       dispatcher.emit_sync(event, loop=manager.loop)
   -----------------------------------------------------------------------------
"""
