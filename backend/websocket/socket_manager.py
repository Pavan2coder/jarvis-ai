import asyncio
from typing import List
from fastapi import WebSocket
from backend.utils import logger

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.loop: asyncio.AbstractEventLoop = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """Sets the active event loop to allow bridging sync-to-async calls."""
        self.loop = loop

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Active connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending message to WebSocket client: {e}")

    async def broadcast(self, message: dict):
        """Broadcasts a JSON message to all connected clients asynchronously."""
        if not self.active_connections:
            return
        # Create a copy to prevent mutation issues during iteration
        connections = list(self.active_connections)
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to client connection: {e}")
                self.disconnect(connection)

    def broadcast_sync(self, message: dict):
        """Bridge allowing non-blocking sync threads to broadcast to WebSocket clients."""
        if not self.loop:
            logger.warning("Event loop not bound in ConnectionManager. Dropping sync broadcast.")
            return
        if self.active_connections:
            asyncio.run_coroutine_threadsafe(self.broadcast(message), self.loop)

# Singleton Connection Manager
manager = ConnectionManager()
