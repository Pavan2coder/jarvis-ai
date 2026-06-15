import unittest
import time
import asyncio
from unittest.mock import AsyncMock, MagicMock
from starlette.websockets import WebSocketState
from backend.websocket.socket_manager import ConnectionManager
from backend.core import config

class MockWebSocket:
    def __init__(self, host="127.0.0.1", port=12345):
        self.client_state = WebSocketState.CONNECTED
        self.application_state = WebSocketState.CONNECTED
        self.close = AsyncMock()
        # Mock connection client property
        client_mock = MagicMock()
        client_mock.host = host
        client_mock.port = port
        self.client = client_mock
        self.accept = AsyncMock()

class TestWebSocketReliability(unittest.TestCase):
    def setUp(self):
        self.manager = ConnectionManager()
        self.loop = asyncio.new_event_loop()
        self.manager.set_loop(self.loop)
        
        # Override config setting for testing
        config.WS_HEARTBEAT_TIMEOUT = 0.5 # 500ms timeout

    def tearDown(self):
        self.loop.close()

    def test_connect_registers_connection(self):
        """Verifies that connect registers connection with metadata and timestamps."""
        ws = MockWebSocket()
        # Run connect in event loop
        self.loop.run_until_complete(self.manager.connect(ws, "client_1"))
        
        self.assertIn(ws, self.manager.active_connections)
        info = self.manager.active_connections[ws]
        self.assertEqual(info["client_id"], "client_1")
        self.assertTrue(time.time() - info["last_message_at"] < 0.1)

    def test_record_activity_updates_timestamp(self):
        """Verifies that record_activity updates the last message timestamp."""
        ws = MockWebSocket()
        self.loop.run_until_complete(self.manager.connect(ws, "client_1"))
        
        info = self.manager.active_connections[ws]
        original_time = info["last_message_at"] - 10.0
        info["last_message_at"] = original_time
        
        self.manager.record_activity(ws)
        self.assertTrue(info["last_message_at"] > original_time)
        self.assertTrue(time.time() - info["last_message_at"] < 0.1)

    def test_stale_connection_pruning(self):
        """Verifies that connections exceeding WS_HEARTBEAT_TIMEOUT are actively pruned."""
        ws_active = MockWebSocket(port=1111)
        ws_stale = MockWebSocket(port=2222)
        
        self.loop.run_until_complete(self.manager.connect(ws_active, "active"))
        self.loop.run_until_complete(self.manager.connect(ws_stale, "stale"))
        
        # Set stale connection's last activity timestamp to 1 second ago (exceeding 0.5s limit)
        self.manager.active_connections[ws_stale]["last_message_at"] = time.time() - 1.0
        
        # Run cleanup
        self.manager.cleanup_dead_connections()
        
        # Stale should be pruned, active should remain
        self.assertNotIn(ws_stale, self.manager.active_connections)
        self.assertIn(ws_active, self.manager.active_connections)
        
        # Stale connection should have close scheduled
        ws_stale.close.assert_called_once_with(code=1008)
        ws_active.close.assert_not_called()

    def test_physical_disconnect_pruning(self):
        """Verifies that physically disconnected connections are cleaned up immediately."""
        ws = MockWebSocket()
        self.loop.run_until_complete(self.manager.connect(ws, "client_1"))
        
        # Set physical state to disconnected
        ws.client_state = WebSocketState.DISCONNECTED
        
        self.manager.cleanup_dead_connections()
        self.assertNotIn(ws, self.manager.active_connections)

if __name__ == "__main__":
    unittest.main()
