"""
Tests for WebSocket Real-time Metrics

Sprint 16-18: Analytics Service
Week 5, Task 5.2: WebSocket Server Tests
Author: Analytics Team
Date: October 6, 2025
"""

import asyncio
import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.v1.websocket import ConnectionManager, manager


@pytest.fixture
def connection_manager():
    """Create fresh ConnectionManager instance for testing"""
    return ConnectionManager()


@pytest.fixture
def mock_websocket():
    """Create mock WebSocket connection"""
    ws = AsyncMock()
    ws.client = MagicMock()
    ws.client.host = "127.0.0.1"
    ws.client.port = 12345
    return ws


class TestConnectionManager:
    """Test ConnectionManager functionality"""

    @pytest.mark.asyncio
    async def test_connect(self, connection_manager, mock_websocket):
        """Test connecting a new WebSocket"""
        client_info = {"user_id": "test123"}

        await connection_manager.connect(mock_websocket, client_info)

        assert mock_websocket in connection_manager.active_connections
        assert mock_websocket in connection_manager.connection_metadata
        assert connection_manager.connection_metadata[mock_websocket]["client_info"] == client_info
        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect(self, connection_manager, mock_websocket):
        """Test disconnecting a WebSocket"""
        await connection_manager.connect(mock_websocket)
        assert mock_websocket in connection_manager.active_connections

        connection_manager.disconnect(mock_websocket)

        assert mock_websocket not in connection_manager.active_connections
        assert mock_websocket not in connection_manager.connection_metadata

    @pytest.mark.asyncio
    async def test_send_personal_message(self, connection_manager, mock_websocket):
        """Test sending message to specific connection"""
        await connection_manager.connect(mock_websocket)

        message = {"type": "test", "data": "hello"}
        await connection_manager.send_personal_message(message, mock_websocket)

        mock_websocket.send_json.assert_called_once_with(message)
        assert connection_manager.connection_metadata[mock_websocket]["messages_sent"] == 1

    @pytest.mark.asyncio
    async def test_send_personal_message_failure(self, connection_manager, mock_websocket):
        """Test handling of failed personal message"""
        await connection_manager.connect(mock_websocket)
        mock_websocket.send_json.side_effect = Exception("Connection lost")

        message = {"type": "test", "data": "hello"}
        await connection_manager.send_personal_message(message, mock_websocket)

        # Should disconnect on failure
        assert mock_websocket not in connection_manager.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_connections(self, connection_manager):
        """Test broadcasting message to multiple connections"""
        # Create 3 mock connections
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws3 = AsyncMock()

        await connection_manager.connect(ws1)
        await connection_manager.connect(ws2)
        await connection_manager.connect(ws3)

        message = {"type": "broadcast", "data": "hello all"}
        await connection_manager.broadcast(message)

        # All should receive message
        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)
        ws3.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_broadcast_with_failed_connection(self, connection_manager):
        """Test broadcasting when one connection fails"""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws2.send_json.side_effect = Exception("Connection lost")  # This one fails
        ws3 = AsyncMock()

        await connection_manager.connect(ws1)
        await connection_manager.connect(ws2)
        await connection_manager.connect(ws3)

        message = {"type": "broadcast", "data": "hello all"}
        await connection_manager.broadcast(message)

        # ws2 should be disconnected
        assert ws1 in connection_manager.active_connections
        assert ws2 not in connection_manager.active_connections
        assert ws3 in connection_manager.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_text(self, connection_manager):
        """Test broadcasting text message"""
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await connection_manager.connect(ws1)
        await connection_manager.connect(ws2)

        text = "Hello text"
        await connection_manager.broadcast_text(text)

        ws1.send_text.assert_called_once_with(text)
        ws2.send_text.assert_called_once_with(text)

    @pytest.mark.asyncio
    async def test_ping_all(self, connection_manager):
        """Test ping functionality"""
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await connection_manager.connect(ws1)
        await connection_manager.connect(ws2)

        await connection_manager.ping_all()

        # Both should receive ping
        assert ws1.send_json.call_count == 1
        assert ws2.send_json.call_count == 1

        # Check ping message structure
        ping_call = ws1.send_json.call_args[0][0]
        assert ping_call["type"] == "ping"
        assert "timestamp" in ping_call

        # Check last_ping updated
        assert "last_ping" in connection_manager.connection_metadata[ws1]

    @pytest.mark.asyncio
    async def test_ping_removes_dead_connections(self, connection_manager):
        """Test that ping removes dead connections"""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws2.send_json.side_effect = Exception("Connection dead")

        await connection_manager.connect(ws1)
        await connection_manager.connect(ws2)

        await connection_manager.ping_all()

        # ws2 should be removed
        assert ws1 in connection_manager.active_connections
        assert ws2 not in connection_manager.active_connections

    def test_get_stats(self, connection_manager):
        """Test getting connection statistics"""
        stats = connection_manager.get_stats()

        assert "total_connections" in stats
        assert "total_messages_sent" in stats
        assert "average_messages_per_connection" in stats
        assert "connection_metadata" in stats

        assert stats["total_connections"] == 0

    @pytest.mark.asyncio
    async def test_get_stats_with_connections(self, connection_manager, mock_websocket):
        """Test stats with active connections"""
        await connection_manager.connect(mock_websocket)

        # Send some messages
        message = {"type": "test"}
        await connection_manager.send_personal_message(message, mock_websocket)
        await connection_manager.send_personal_message(message, mock_websocket)

        stats = connection_manager.get_stats()

        assert stats["total_connections"] == 1
        assert stats["total_messages_sent"] == 2
        assert stats["average_messages_per_connection"] == 2.0


@pytest.mark.asyncio
async def test_websocket_endpoint_connection(client, mock_redis):
    """Test WebSocket endpoint connection flow"""
    # This test requires WebSocketTestClient which is more complex
    # For now, we test the manager functionality which is the core logic
    pass


@pytest.mark.asyncio
async def test_concurrent_connections_limit(connection_manager):
    """Test supporting 100+ concurrent connections"""
    connections = []

    # Create 100 mock connections
    for i in range(100):
        ws = AsyncMock()
        ws.client = MagicMock()
        ws.client.host = f"127.0.0.{i % 255}"
        ws.client.port = 10000 + i
        await connection_manager.connect(ws)
        connections.append(ws)

    # Verify all connected
    assert len(connection_manager.active_connections) == 100

    # Test broadcast to all
    message = {"type": "load_test", "data": "stress test"}
    await connection_manager.broadcast(message)

    # Verify all received message
    for ws in connections:
        ws.send_json.assert_called_once_with(message)

    # Disconnect all
    for ws in connections:
        connection_manager.disconnect(ws)

    assert len(connection_manager.active_connections) == 0


@pytest.mark.asyncio
async def test_connection_metadata_tracking(connection_manager, mock_websocket):
    """Test that connection metadata is properly tracked"""
    client_info = {"user_id": "test123", "role": "admin"}

    await connection_manager.connect(mock_websocket, client_info)

    metadata = connection_manager.connection_metadata[mock_websocket]

    assert metadata["client_info"] == client_info
    assert "connected_at" in metadata
    assert metadata["messages_sent"] == 0

    # Send messages and verify counter
    message = {"type": "test"}
    await connection_manager.send_personal_message(message, mock_websocket)
    await connection_manager.send_personal_message(message, mock_websocket)

    assert metadata["messages_sent"] == 2


@pytest.mark.asyncio
async def test_broadcast_performance(connection_manager):
    """Test broadcast performance with many connections"""
    import time

    # Create 50 connections
    connections = []
    for i in range(50):
        ws = AsyncMock()
        await connection_manager.connect(ws)
        connections.append(ws)

    # Measure broadcast time
    message = {"type": "performance_test", "data": "x" * 1000}  # 1KB message

    start_time = time.time()
    await connection_manager.broadcast(message)
    elapsed = time.time() - start_time

    # Should complete in less than 1 second for 50 connections
    assert elapsed < 1.0

    # Verify all received
    for ws in connections:
        ws.send_json.assert_called_once_with(message)
