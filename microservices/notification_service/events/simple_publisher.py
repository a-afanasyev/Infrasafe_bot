# Simplified Event Publisher
# UK Management Bot - Notification Service

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
import redis.asyncio as redis

from config import settings

logger = logging.getLogger(__name__)

class SimpleEventPublisher:
    """Simplified event publisher without external dependencies"""

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.is_connected = False

    async def initialize(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30
            )

            # Test connection
            await self.redis_client.ping()
            self.is_connected = True
            logger.info("Event publisher initialized successfully")

        except Exception as e:
            logger.warning(f"Failed to initialize event publisher: {e}")
            self.is_connected = False

    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            try:
                await self.redis_client.close()
                self.is_connected = False
                logger.info("Event publisher closed")
            except Exception as e:
                logger.warning(f"Error closing event publisher: {e}")

    async def publish(self, event_type: str, data: Dict[str, Any], correlation_id: str = None) -> bool:
        """Publish event to Redis stream"""
        if not self.is_connected or not self.redis_client:
            logger.warning(f"Cannot publish event {event_type} - not connected to Redis")
            return False

        try:
            event_id = str(uuid.uuid4())
            correlation_id = correlation_id or str(uuid.uuid4())

            event_data = {
                "event_id": event_id,
                "event_type": event_type,
                "correlation_id": correlation_id,
                "timestamp": datetime.utcnow().isoformat(),
                "service": settings.service_name,
                "data": json.dumps(data)
            }

            # Use Redis streams for reliable event delivery
            stream_key = f"events:{event_type}"
            await self.redis_client.xadd(stream_key, event_data)

            # Also publish to pub/sub for immediate consumption
            channel = f"notifications:{event_type}"
            await self.redis_client.publish(channel, json.dumps(event_data))

            logger.info(f"Published event {event_type} with ID {event_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to publish event {event_type}: {e}")
            return False

    async def publish_notification_sent(self, notification_id: int, notification_type: str, status: str, recipient_id: int = None):
        """Publish notification sent event"""
        data = {
            "notification_id": notification_id,
            "notification_type": notification_type,
            "status": status,
            "recipient_id": recipient_id
        }
        return await self.publish("notification_sent", data)

    async def publish_notification_delivered(self, notification_id: int, delivery_time: datetime):
        """Publish notification delivered event"""
        data = {
            "notification_id": notification_id,
            "delivered_at": delivery_time.isoformat()
        }
        return await self.publish("notification_delivered", data)

    async def publish_notification_failed(self, notification_id: int, error: str, retry_count: int):
        """Publish notification failed event"""
        data = {
            "notification_id": notification_id,
            "error": error,
            "retry_count": retry_count
        }
        return await self.publish("notification_failed", data)

    async def health_check(self) -> Dict[str, Any]:
        """Check event publisher health"""
        if not self.redis_client:
            return {"status": "disconnected", "error": "Redis client not initialized"}

        try:
            await self.redis_client.ping()
            return {"status": "healthy", "connected": True}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e), "connected": False}