from fastapi import APIRouter
from backend.api.ui_server import ui_state
from backend.system import system_ops

router = APIRouter()

@router.get("/state")
async def get_state():
    """Returns the current J.A.R.V.I.S UI state dictionary."""
    return ui_state

@router.get("/stats")
async def get_stats():
    """Returns live system diagnostic metrics (CPU, RAM, GPU, Battery)."""
    return system_ops.get_live_stats()

@router.get("/health")
async def get_health():
    """Simple health check verification endpoint."""
    return {"status": "healthy"}
