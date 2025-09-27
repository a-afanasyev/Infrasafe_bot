# Simplified Event Subscriber
# UK Management Bot - Notification Service

import asyncio
import json
import logging
from typing import Dict, Any, Optional, Callable, List
import redis.asyncio as redis

from config import settings

logger = logging.getLogger(__name__)

class SimpleEventSubscriber:
    """Simplified event subscriber without external dependencies"""

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.PubSub] = None
        self.is_connected = False
        self.handlers: Dict[str, List[Callable]] = {}
        self.running = False

    async def initialize(self):
        """Initialize Redis connection and pub/sub"""
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

            self.pubsub = self.redis_client.pubsub()
            self.is_connected = True

            logger.info("Event subscriber initialized successfully")

        except Exception as e:
            logger.warning(f"Failed to initialize event subscriber: {e}")
            self.is_connected = False

    async def close(self):
        """Close connections and stop listening"""
        self.running = False

        if self.pubsub:
            try:
                await self.pubsub.close()
            except Exception as e:
                logger.warning(f"Error closing pubsub: {e}")

        if self.redis_client:
            try:
                await self.redis_client.close()
                self.is_connected = False
                logger.info("Event subscriber closed")
            except Exception as e:
                logger.warning(f"Error closing event subscriber: {e}")

    def register_handler(self, event_type: str, handler: Callable):
        """Register event handler"""
        if event_type not in self.handlers:
            self.handlers[event_type] = []

        self.handlers[event_type].append(handler)
        logger.info(f"Registered handler for event type: {event_type}")

    async def subscribe(self, event_types: List[str]):
        """Subscribe to event types"""
        if not self.is_connected or not self.pubsub:
            logger.warning("Cannot subscribe - not connected to Redis")
            return

        try:
            channels = [f"notifications:{event_type}" for event_type in event_types]
            await self.pubsub.subscribe(*channels)
            logger.info(f"Subscribed to channels: {channels}")

        except Exception as e:
            logger.error(f"Failed to subscribe to events: {e}")

    async def start_listening(self):
        """Start listening for events"""
        if not self.is_connected or not self.pubsub:
            logger.warning("Cannot start listening - not connected")
            return

        self.running = True
        logger.info("Started event listener")

        try:
            async for message in self.pubsub.listen():
                if not self.running:
                    break

                if message["type"] != "message":
                    continue

                try:
                    # Parse channel to get event type
                    channel = message["channel"]
                    if not channel.startswith("notifications:"):
                        continue

                    event_type = channel.replace("notifications:", "")

                    # Parse event data
                    event_data = json.loads(message["data"])

                    # Call handlers
                    await self._handle_event(event_type, event_data)

                except Exception as e:
                    logger.error(f"Error processing event message: {e}")

        except Exception as e:
            logger.error(f"Error in event listener: {e}")

    async def _handle_event(self, event_type: str, event_data: Dict[str, Any]):
        """Handle received event"""
        if event_type not in self.handlers:
            logger.debug(f"No handlers registered for event type: {event_type}")
            return

        for handler in self.handlers[event_type]:
            try:
                await handler(event_data)
            except Exception as e:
                logger.error(f"Error in event handler for {event_type}: {e}")

    async def health_check(self) -> Dict[str, Any]:
        """Check event subscriber health"""
        if not self.redis_client:
            return {"status": "disconnected", "error": "Redis client not initialized"}

        try:
            await self.redis_client.ping()
            return {
                "status": "healthy",
                "connected": True,
                "running": self.running,
                "handlers_count": sum(len(handlers) for handlers in self.handlers.values())
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e), "connected": False}

# Example event handlers for notification service
async def handle_user_registered(event_data: Dict[str, Any]):
    """Handle user registration event"""
    logger.info(f"User registered: {event_data}")
    # Here we could send welcome notification

async def handle_request_status_changed(event_data: Dict[str, Any]):
    """Handle request status change event"""
    logger.info(f"Request status changed: {event_data}")
    # Here we could send status notification

async def handle_shift_started(event_data: Dict[str, Any]):
    """Handle shift started event"""
    logger.info(f"Shift started: {event_data}")
    # Here we could send shift notification