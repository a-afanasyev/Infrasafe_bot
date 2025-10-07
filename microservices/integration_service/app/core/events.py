"""
Event Publishing System
UK Management Bot - Integration Service

Publishes integration events to message bus for other services.
"""

import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class EventPublisher:
    """
    Event publisher for integration events.

    Uses Redis Pub/Sub for real-time event distribution.
    Other services can subscribe to integration events.
    """

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client
        self._connected = False

    async def connect(self):
        """Connect to Redis"""
        if not self.redis:
            self.redis = await redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
        self._connected = True
        logger.info("✅ Event Publisher connected to Redis")

    async def disconnect(self):
        """Disconnect from Redis"""
        if self.redis:
            await self.redis.close()
            self._connected = False
            logger.info("👋 Event Publisher disconnected")

    async def publish(
        self,
        event_type: str,
        data: Dict[str, Any],
        tenant_id: Optional[str] = None
    ):
        """
        Publish event to Redis Pub/Sub.

        Args:
            event_type: Event type (e.g., "webhook.stripe.payment.succeeded")
            data: Event data
            tenant_id: Optional tenant ID for multi-tenancy

        Channel naming:
            integration.{event_type}
            Example: integration.webhook.stripe.payment.succeeded
        """
        if not self._connected:
            await self.connect()

        # Build event message
        event_message = {
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
            "source": "integration_service",
            "tenant_id": tenant_id
        }

        # Publish to Redis channel
        channel = f"integration.{event_type}"

        try:
            await self.redis.publish(
                channel,
                json.dumps(event_message)
            )
            logger.debug(f"📢 Published event: {channel}")

        except Exception as e:
            logger.error(f"Failed to publish event {event_type}: {e}")

    async def publish_webhook_event(
        self,
        source: str,
        event_type: str,
        event_id: str,
        data: Dict[str, Any]
    ):
        """Publish webhook event."""
        await self.publish(
            event_type=f"webhook.{source}.{event_type}",
            data={
                "event_id": event_id,
                "source": source,
                "event_type": event_type,
                **data
            }
        )

    async def publish_integration_event(
        self,
        integration_type: str,
        operation: str,
        success: bool,
        data: Dict[str, Any]
    ):
        """Publish integration operation event."""
        await self.publish(
            event_type=f"integration.{integration_type}.{operation}",
            data={
                "success": success,
                "integration_type": integration_type,
                "operation": operation,
                **data
            }
        )


# Global event publisher instance
_event_publisher: Optional[EventPublisher] = None


async def get_event_publisher() -> EventPublisher:
    """Get global event publisher instance."""
    global _event_publisher

    if _event_publisher is None:
        _event_publisher = EventPublisher()
        await _event_publisher.connect()

    return _event_publisher


async def init_event_publisher():
    """Initialize event publisher on startup."""
    global _event_publisher
    _event_publisher = EventPublisher()
    await _event_publisher.connect()
    logger.info("🚀 Event Publisher initialized")


async def shutdown_event_publisher():
    """Shutdown event publisher on application shutdown."""
    global _event_publisher
    if _event_publisher:
        await _event_publisher.disconnect()
        _event_publisher = None
