from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.websocket.socket_manager import manager
from backend.api.ui_server import ui_state
from backend.utils import logger

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket connection handler route."""
    await manager.connect(websocket)
    # Send the current state immediately upon connection
    await manager.send_personal_message(ui_state, websocket)
    try:
        while True:
            # Keep socket alive and receive JSON payloads (if any sent by clients)
            data = await websocket.receive_json()
            logger.info(f"Received WebSocket data: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        manager.disconnect(websocket)
