import uvicorn
from backend.utils import logger

# Global UI state accessed by engines and API routes
ui_state = {
    "status": "idle",        # idle | listening | thinking | speaking
    "message": "Standing by...",
    "wake_source": "",
    "command": "",
    "response": "",
}

def start_ui_server():
    """Starts the FastAPI app using Uvicorn on port 5050."""
    logger.info("Starting FastAPI server bridge via Uvicorn...")
    uvicorn.run("backend.api.server:app", host="localhost", port=5050, log_level="warning")

def set_ui(status, message="", command="", response="", wake_source=""):
    """Exposed state modifier utility invoked by backend triggers."""
    ui_state["status"]     = status
    ui_state["message"]    = message or ui_state["message"]
    ui_state["command"]    = command
    ui_state["response"]   = response
    ui_state["wake_source"] = wake_source

    try:
        from backend.websocket.events import dispatcher, JarvisEvent, JarvisEventType
        from backend.websocket.socket_manager import manager
        
        event_name = JarvisEventType.SYSTEM_UPDATE
        if status == "listening":
            event_name = JarvisEventType.AI_LISTENING
        elif status == "thinking":
            event_name = JarvisEventType.AI_THINKING
        elif status == "speaking":
            event_name = JarvisEventType.AI_SPEAKING
            
        event = JarvisEvent(event_name, data=ui_state)
        dispatcher.emit_sync(event, loop=manager.loop)
    except Exception as e:
        logger.error(f"Failed to emit UI state event: {e}")

