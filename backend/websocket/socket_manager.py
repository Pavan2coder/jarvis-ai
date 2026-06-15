import asyncio
import time
from typing import Dict, List, Any
from fastapi import WebSocket
from starlette.websockets import WebSocketState
from backend.utils import logger

class ConnectionManager:
    def __init__(self):
        # Map active WebSocket connections to their metadata dict
        self.active_connections: Dict[WebSocket, Dict[str, Any]] = {}
        self.loop: asyncio.AbstractEventLoop = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """Sets the active event loop to allow bridging sync-to-async calls."""
        self.loop = loop

    async def connect(self, websocket: WebSocket, client_id: str = None):
        """Registers a new WebSocket client and accepts the connection."""
        await websocket.accept()
        
        # Gather connection details
        client_address = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"
        cid = client_id or f"client_{client_address}_{int(time.time())}"
        
        self.active_connections[websocket] = {
            "client_id": cid,
            "connected_at": time.time(),
            "status": "connected",
            "last_message_at": time.time(),
            "address": client_address
        }
        
        logger.info(f"WebSocket client '{cid}' connected from {client_address}. Active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Removes a client from active tracking."""
        if websocket in self.active_connections:
            client_info = self.active_connections.pop(websocket)
            logger.info(f"WebSocket client '{client_info['client_id']}' disconnected. Active connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Sends a JSON message to a single client with automatic error recovery."""
        self.cleanup_dead_connections()
        if websocket not in self.active_connections:
            logger.warning("Attempted to send message to an inactive or disconnected WebSocket.")
            return

        try:
            await websocket.send_json(message)
            self.active_connections[websocket]["last_message_at"] = time.time()
        except Exception as e:
            logger.error(f"Error sending message to client '{self.active_connections[websocket]['client_id']}': {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: dict):
        """Broadcasts a JSON message to all connected clients asynchronously with error recovery."""
        self.cleanup_dead_connections()
        if not self.active_connections:
            return

        # Create a copy of keys to avoid modification during iteration
        connections = list(self.active_connections.keys())
        for connection in connections:
            try:
                if (connection.client_state == WebSocketState.CONNECTED and 
                    connection.application_state == WebSocketState.CONNECTED):
                    await connection.send_json(message)
                    if connection in self.active_connections:
                        self.active_connections[connection]["last_message_at"] = time.time()
                else:
                    self.disconnect(connection)
            except Exception as e:
                client_id = self.active_connections[connection]["client_id"] if connection in self.active_connections else "unknown"
                logger.error(f"Error broadcasting to client '{client_id}': {e}")
                self.disconnect(connection)

    def broadcast_sync(self, message: dict):
        """Bridge allowing non-blocking sync threads to broadcast to WebSocket clients."""
        if not self.loop:
            logger.warning("Event loop not bound in ConnectionManager. Dropping sync broadcast.")
            return
        if self.active_connections:
            asyncio.run_coroutine_threadsafe(self.broadcast(message), self.loop)

    def get_client_status(self) -> List[Dict[str, Any]]:
        """Returns the status and metadata for all active client connections."""
        self.cleanup_dead_connections()
        return [
            {
                "client_id": info["client_id"],
                "connected_at": info["connected_at"],
                "last_message_at": info["last_message_at"],
                "address": info["address"],
                "status": info["status"]
            }
            for info in self.active_connections.values()
        ]

    def record_activity(self, websocket: WebSocket):
        """Updates the last message activity timestamp for a connection."""
        if websocket in self.active_connections:
            self.active_connections[websocket]["last_message_at"] = time.time()

    def cleanup_dead_connections(self):
        """Scans and cleans up any stale or disconnected WebSocket connections."""
        from backend.core import config
        timeout = getattr(config, "WS_HEARTBEAT_TIMEOUT", 30.0)
        now = time.time()
        
        connections = list(self.active_connections.keys())
        for connection in connections:
            info = self.active_connections[connection]
            
            is_physically_disconnected = (
                connection.client_state == WebSocketState.DISCONNECTED or 
                connection.application_state == WebSocketState.DISCONNECTED
            )
            
            is_inactive = (now - info["last_message_at"]) > timeout
            
            if is_physically_disconnected or is_inactive:
                reason = "physical disconnect" if is_physically_disconnected else f"heartbeat timeout (> {timeout}s)"
                logger.warning(f"Cleaning up dead connection ({reason}): {info['client_id']}")
                self.disconnect(connection)
                
                # Actively close connection on heartbeat timeout
                if is_inactive and not is_physically_disconnected:
                    try:
                        loop = self.loop or asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.run_coroutine_threadsafe(connection.close(code=1008), loop)
                        else:
                            loop.run_until_complete(connection.close(code=1008))
                    except Exception as e:
                        logger.error(f"Error actively closing stale connection: {e}")

# Singleton Connection Manager
manager = ConnectionManager()
