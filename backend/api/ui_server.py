import uvicorn
from backend.utils import logger

from ui.state_manager import state_manager

class UIStateProxy(dict):
    """Thread-safe dictionary proxy that delegates reads and writes to state_manager."""
    def __getitem__(self, key):
        return state_manager.get_snapshot()[key]
        
    def get(self, key, default=None):
        return state_manager.get_snapshot().get(key, default)
        
    def __setitem__(self, key, value):
        state_manager.update_state(**{key: value})
        
    def __repr__(self):
        return repr(state_manager.get_snapshot())
        
    def keys(self):
        return state_manager.get_snapshot().keys()
        
    def values(self):
        return state_manager.get_snapshot().values()
        
    def items(self):
        return state_manager.get_snapshot().items()
        
    def copy(self):
        return state_manager.get_snapshot()
        
    def __len__(self):
        return len(state_manager.get_snapshot())
        
    def __contains__(self, item):
        return item in state_manager.get_snapshot()

# Global UI state proxy accessed by engines and API routes
ui_state = UIStateProxy()

def start_ui_server():
    """Starts the FastAPI app using Uvicorn on port 5050."""
    logger.info("Starting FastAPI server bridge via Uvicorn...")
    uvicorn.run("backend.api.server:app", host="localhost", port=5050, log_level="warning")

def set_ui(status, message="", command="", response="", wake_source=""):
    """Exposed state modifier utility invoked by backend triggers."""
    state_manager.update_state(
        status=status,
        message=message,
        command=command,
        response=response,
        wake_source=wake_source
    )


