from fastapi import APIRouter
from ui.state_manager import state_manager
from backend.system import system_ops

router = APIRouter()

@router.get("/state")
async def get_state():
    """Returns the current J.A.R.V.I.S UI state dictionary."""
    return state_manager.get_snapshot()

@router.get("/state/diagnostics")
async def get_state_diagnostics():
    """Returns lock contention, reads, writes, and subscriber counts for diagnostics."""
    return state_manager.get_diagnostics()

@router.get("/stats")
async def get_stats():
    """Returns live system diagnostic metrics (CPU, RAM, GPU, Battery)."""
    return system_ops.get_live_stats()

@router.get("/health")
async def get_health():
    """Simple health check verification endpoint."""
    return {"status": "healthy"}

