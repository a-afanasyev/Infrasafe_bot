"""
WebSocket API - Real-time Metrics Broadcasting

Sprint 16-18: Analytics Service
Week 5, Task 5.2: WebSocket Server Implementation
Author: Analytics Team
Date: October 6, 2025
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Set, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from redis import asyncio as aioredis

from config.settings import settings
from db.session import get_redis
from services.kpi_calculator import KPICalculator

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """
    Manages WebSocket connections for real-time metric broadcasting.

    Features:
    - Connection lifecycle management
    - Message broadcasting to all connected clients
    - Automatic cleanup on disconnect
    - Heartbeat/ping-pong for connection health
    - Support for 100+ concurrent connections
    """

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.connection_metadata: Dict[WebSocket, dict] = {}
        self._broadcast_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket, client_info: dict = None) -> None:
        """
        Accept new WebSocket connection and register it.

        Args:
            websocket: FastAPI WebSocket instance
            client_info: Optional metadata about the client
        """
        await websocket.accept()
        self.active_connections.add(websocket)
        self.connection_metadata[websocket] = {
            "connected_at": datetime.utcnow().isoformat(),
            "client_info": client_info or {},
            "messages_sent": 0,
            "last_ping": datetime.utcnow().isoformat()
        }
        logger.info(
            f"✅ WebSocket connected: {len(self.active_connections)} active connections"
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove WebSocket connection from active set.

        Args:
            websocket: FastAPI WebSocket instance to disconnect
        """
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            metadata = self.connection_metadata.pop(websocket, {})
            logger.info(
                f"❌ WebSocket disconnected: {len(self.active_connections)} active, "
                f"sent {metadata.get('messages_sent', 0)} messages"
            )

    async def send_personal_message(self, message: dict, websocket: WebSocket) -> None:
        """
        Send message to specific WebSocket connection.

        Args:
            message: Dictionary to send (will be JSON-encoded)
            websocket: Target WebSocket connection
        """
        try:
            await websocket.send_json(message)
            if websocket in self.connection_metadata:
                self.connection_metadata[websocket]["messages_sent"] += 1
        except Exception as e:
            logger.error(f"❌ Failed to send personal message: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: dict) -> None:
        """
        Broadcast message to all connected clients.

        Args:
            message: Dictionary to broadcast (will be JSON-encoded)
        """
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
                if connection in self.connection_metadata:
                    self.connection_metadata[connection]["messages_sent"] += 1
            except Exception as e:
                logger.error(f"❌ Failed to broadcast to connection: {e}")
                disconnected.append(connection)

        # Clean up failed connections
        for connection in disconnected:
            self.disconnect(connection)

    async def broadcast_text(self, text: str) -> None:
        """
        Broadcast text message to all connected clients.

        Args:
            text: Text message to broadcast
        """
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_text(text)
                if connection in self.connection_metadata:
                    self.connection_metadata[connection]["messages_sent"] += 1
            except Exception as e:
                logger.error(f"❌ Failed to broadcast text to connection: {e}")
                disconnected.append(connection)

        # Clean up failed connections
        for connection in disconnected:
            self.disconnect(connection)

    async def ping_all(self) -> None:
        """
        Send ping to all connections to check health.
        Updates last_ping timestamp for each connection.
        """
        ping_message = {
            "type": "ping",
            "timestamp": datetime.utcnow().isoformat()
        }

        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_json(ping_message)
                if connection in self.connection_metadata:
                    self.connection_metadata[connection]["last_ping"] = datetime.utcnow().isoformat()
            except Exception as e:
                logger.warning(f"⚠️ Connection failed ping: {e}")
                disconnected.append(connection)

        # Clean up failed connections
        for connection in disconnected:
            self.disconnect(connection)

    def get_stats(self) -> dict:
        """
        Get connection statistics.

        Returns:
            Dictionary with connection stats
        """
        total_messages_sent = sum(
            meta.get("messages_sent", 0)
            for meta in self.connection_metadata.values()
        )

        return {
            "total_connections": len(self.active_connections),
            "total_messages_sent": total_messages_sent,
            "average_messages_per_connection": (
                total_messages_sent / len(self.active_connections)
                if self.active_connections else 0
            ),
            "connection_metadata": [
                {
                    "connected_at": meta.get("connected_at"),
                    "messages_sent": meta.get("messages_sent", 0),
                    "last_ping": meta.get("last_ping")
                }
                for meta in self.connection_metadata.values()
            ]
        }


# Global connection manager instance
manager = ConnectionManager()


async def broadcast_metrics_periodically(redis_client: aioredis.Redis) -> None:
    """
    Background task to broadcast metrics to all connected clients.

    This task runs continuously and broadcasts metrics every 5 seconds.
    Fetches real-time KPIs and sends them to all WebSocket connections.

    Args:
        redis_client: Redis client for caching
    """
    from services.realtime_kpi_service import get_realtime_service

    realtime_service = get_realtime_service(redis_client)

    while True:
        try:
            # Fetch all real-time metrics
            realtime_data = await realtime_service.get_all_realtime_metrics()

            # Format for WebSocket broadcast
            metrics = {
                "type": "metrics_update",
                "timestamp": datetime.utcnow().isoformat(),
                "data": {
                    "active_connections": len(manager.active_connections),
                    "active_shifts": realtime_data["metrics"]["active_shifts"]["value"],
                    "requests_in_progress": realtime_data["metrics"]["requests_in_progress"]["value"],
                    "active_users": realtime_data["metrics"]["active_users"]["value"],
                    # Include detailed breakdown
                    "details": {
                        "active_shifts": realtime_data["metrics"]["active_shifts"],
                        "requests_in_progress": realtime_data["metrics"]["requests_in_progress"],
                        "active_users": realtime_data["metrics"]["active_users"]
                    }
                }
            }

            # Broadcast to all connections
            await manager.broadcast(metrics)

            logger.debug(
                f"📡 Broadcasted metrics to {len(manager.active_connections)} connections"
            )

        except Exception as e:
            logger.error(f"❌ Error broadcasting metrics: {e}")

        # Wait 5 seconds before next broadcast
        await asyncio.sleep(5)


async def heartbeat_task() -> None:
    """
    Background task to send periodic pings to all connections.

    Sends ping every 30 seconds to detect dead connections.
    """
    while True:
        try:
            await manager.ping_all()
            logger.debug(
                f"💓 Heartbeat sent to {len(manager.active_connections)} connections"
            )
        except Exception as e:
            logger.error(f"❌ Error in heartbeat task: {e}")

        # Wait 30 seconds before next ping
        await asyncio.sleep(30)


@router.websocket("/ws/metrics")
async def websocket_metrics_endpoint(
    websocket: WebSocket,
    redis_client: aioredis.Redis = Depends(get_redis)
):
    """
    WebSocket endpoint for real-time metrics streaming.

    Protocol:
    - Client connects to ws://host:port/api/v1/ws/metrics
    - Server sends periodic metric updates every 5 seconds
    - Server sends ping every 30 seconds
    - Client can send pong to acknowledge ping

    Message Format:
    {
        "type": "metrics_update" | "ping" | "pong" | "error",
        "timestamp": "2025-10-06T12:00:00Z",
        "data": {...}
    }

    Args:
        websocket: WebSocket connection
        redis_client: Redis client dependency
    """
    client_info = {
        "host": websocket.client.host if websocket.client else "unknown",
        "port": websocket.client.port if websocket.client else 0
    }

    await manager.connect(websocket, client_info)

    try:
        # Send welcome message
        await manager.send_personal_message(
            {
                "type": "welcome",
                "message": "Connected to Analytics Service real-time metrics",
                "timestamp": datetime.utcnow().isoformat(),
                "broadcast_interval_seconds": 5,
                "heartbeat_interval_seconds": 30
            },
            websocket
        )

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for incoming messages (pong, subscription updates, etc.)
                data = await websocket.receive_json()

                # Handle pong responses
                if data.get("type") == "pong":
                    logger.debug("📥 Received pong from client")
                    if websocket in manager.connection_metadata:
                        manager.connection_metadata[websocket]["last_pong"] = datetime.utcnow().isoformat()

                # Handle other message types as needed
                elif data.get("type") == "subscribe":
                    # Future: Allow clients to subscribe to specific metrics
                    logger.info(f"📥 Subscription request: {data.get('metrics', [])}")
                    await manager.send_personal_message(
                        {
                            "type": "subscribed",
                            "metrics": data.get("metrics", []),
                            "timestamp": datetime.utcnow().isoformat()
                        },
                        websocket
                    )

            except asyncio.TimeoutError:
                # No message received, continue loop
                continue

    except WebSocketDisconnect:
        logger.info("🔌 Client disconnected normally")
        manager.disconnect(websocket)

    except Exception as e:
        logger.error(f"❌ WebSocket error: {e}")
        try:
            await manager.send_personal_message(
                {
                    "type": "error",
                    "message": "Internal server error",
                    "timestamp": datetime.utcnow().isoformat()
                },
                websocket
            )
        except:
            pass
        manager.disconnect(websocket)


@router.get("/ws/stats")
async def get_websocket_stats():
    """
    Get WebSocket connection statistics.

    Returns:
        Connection statistics including active connections and message counts
    """
    return manager.get_stats()


@router.post("/ws/broadcast")
async def broadcast_message(message: dict):
    """
    Manually broadcast a message to all connected WebSocket clients.

    Useful for testing or administrative notifications.

    Args:
        message: Dictionary to broadcast

    Returns:
        Broadcast status
    """
    try:
        await manager.broadcast(message)
        return {
            "status": "success",
            "message": "Broadcast sent",
            "connections": len(manager.active_connections),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ Broadcast failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
