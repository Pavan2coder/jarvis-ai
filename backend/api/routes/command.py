from fastapi import APIRouter, Query, BackgroundTasks
from backend.assistant import commands
from backend.api import ui_server
from backend.utils import logger

router = APIRouter()

@router.get("/command")
async def run_command(text: str = Query(...), background_tasks: BackgroundTasks = None):
    """Triggers execution of a text command asynchronously in the background."""
    text = text.strip()
    if text:
        logger.info(f"Received API command request: '{text}'")
        ui_server.set_ui("thinking", message="Processing command...", command=text)
        if background_tasks:
            background_tasks.add_task(commands.handle_command, text)
        return {"status": "ok", "message": f"Command '{text}' queued."}
    return {"status": "error", "message": "Command text cannot be empty."}
