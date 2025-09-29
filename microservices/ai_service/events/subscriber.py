# Event Subscriber
# UK Management Bot - Microservices Event Architecture

import asyncio
import json
import logging
from typing import Dict, Any, Optional, Callable, List, Set
from datetime import datetime
import redis.asyncio as redis
from pydantic import BaseModel

from ..config import settings
from ...shared.events.schema_registry import EventType, EventVersion, BaseEvent, get_schema_registry
from ..middleware.tracing import get_tracer, add_span_attributes

logger = logging.getLogger(__name__)

EventHandler = Callable[[BaseModel], None]

class EventSubscriber:
    """Redis-based event subscriber with consumer groups"""

    def __init__(self, redis_url: str = None, consumer_group: str = None):
        self.redis_url = redis_url or settings.redis_url
        self.consumer_group = consumer_group or f"{settings.service_name}-consumer"
        self.consumer_name = f"{self.consumer_group}-{settings.service_name}"
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub_client: Optional[redis.Redis] = None
        self.is_connected = False
        self.handlers: Dict[EventType, List[EventHandler]] = {}
        self.running = False
        self.schema_registry = get_schema_registry()
        self.tracer = get_tracer()
        self.subscribed_events: Set[EventType] = set()

    async def initialize(self):
        """Initialize Redis connections"""
        try:
            # Stream consumer client
            self.redis_client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_keepalive=True,
                health_check_interval=30
            )

            # Pub/Sub client (separate connection)
            self.pubsub_client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )

            # Test connections
            await self.redis_client.ping()
            await self.pubsub_client.ping()

            self.is_connected = True
            logger.info("Event subscriber initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize event subscriber: {e}")
            self.is_connected = False
            raise

    async def close(self):
        """Close Redis connections"""
        self.running = False

        if self.redis_client:
            await self.redis_client.close()

        if self.pubsub_client:
            await self.pubsub_client.close()

        self.is_connected = False
        logger.info("Event subscriber closed")

    def subscribe(self, event_type: EventType, handler: EventHandler):
        """Subscribe to an event type with handler"""
        if event_type not in self.handlers:
            self.handlers[event_type] = []

        self.handlers[event_type].append(handler)
        self.subscribed_events.add(event_type)
        logger.info(f"Subscribed to {event_type.value}")

    def unsubscribe(self, event_type: EventType, handler: EventHandler = None):
        """Unsubscribe from an event type"""
        if event_type in self.handlers:
            if handler:
                self.handlers[event_type].remove(handler)
                if not self.handlers[event_type]:
                    del self.handlers[event_type]
                    self.subscribed_events.discard(event_type)
            else:
                del self.handlers[event_type]
                self.subscribed_events.discard(event_type)

        logger.info(f"Unsubscribed from {event_type.value}")

    async def start_consuming(self):
        """Start consuming events from both streams and pub/sub"""
        if not self.is_connected:
            raise RuntimeError("Event subscriber not initialized")

        self.running = True
        logger.info("Starting event consumption")

        # Start both stream and pub/sub consumers concurrently
        await asyncio.gather(
            self._consume_from_streams(),
            self._consume_from_pubsub(),
            return_exceptions=True
        )

    async def _consume_from_streams(self):
        """Consume events from Redis streams for reliability"""
        while self.running:
            try:
                # Create consumer groups for subscribed events
                await self._ensure_consumer_groups()

                # Read from all subscribed streams
                streams = {
                    f"events:{event_type.value}": ">"
                    for event_type in self.subscribed_events
                }

                if not streams:
                    await asyncio.sleep(1)
                    continue

                # Read messages from streams
                messages = await self.redis_client.xreadgroup(
                    self.consumer_group,
                    self.consumer_name,
                    streams,
                    count=10,
                    block=1000  # Block for 1 second
                )

                for stream, msgs in messages:
                    for msg_id, fields in msgs:
                        await self._handle_stream_message(stream, msg_id, fields)

            except Exception as e:
                logger.error(f"Error in stream consumer: {e}")
                await asyncio.sleep(5)

    async def _consume_from_pubsub(self):
        """Consume events from Redis pub/sub for real-time processing"""
        pubsub = self.pubsub_client.pubsub()

        try:
            # Subscribe to channels
            channels = [f"events.{event_type.value}" for event_type in self.subscribed_events]
            if channels:
                await pubsub.subscribe(*channels)

            while self.running:
                try:
                    message = await pubsub.get_message(timeout=1.0)
                    if message and message["type"] == "message":
                        await self._handle_pubsub_message(message)

                except Exception as e:
                    logger.error(f"Error in pub/sub consumer: {e}")
                    await asyncio.sleep(1)

        finally:
            await pubsub.unsubscribe()
            await pubsub.close()

    async def _ensure_consumer_groups(self):
        """Ensure consumer groups exist for all subscribed streams"""
        for event_type in self.subscribed_events:
            stream_name = f"events:{event_type.value}"
            try:
                await self.redis_client.xgroup_create(
                    stream_name, self.consumer_group, id="0", mkstream=True
                )
            except redis.ResponseError as e:
                # Group already exists
                if "BUSYGROUP" not in str(e):
                    logger.warning(f"Failed to create consumer group for {stream_name}: {e}")

    async def _handle_stream_message(self, stream: str, msg_id: str, fields: Dict[str, Any]):
        """Handle message from Redis stream"""
        with self.tracer.start_as_current_span("event.handle_stream") as span:
            try:
                event_data = fields.get("event_data")
                if not event_data:
                    return

                # Extract event type from stream name
                event_type_str = stream.replace("events:", "")
                event_type = EventType(event_type_str)

                add_span_attributes(span,
                    event_type=event_type_str,
                    stream=stream,
                    message_id=msg_id
                )

                # Deserialize and handle event
                await self._process_event(event_type, event_data)

                # Acknowledge message
                await self.redis_client.xack(stream, self.consumer_group, msg_id)

            except Exception as e:
                logger.error(f"Failed to handle stream message {msg_id}: {e}")
                add_span_attributes(span, error=str(e))

    async def _handle_pubsub_message(self, message: Dict[str, Any]):
        """Handle message from Redis pub/sub"""
        with self.tracer.start_as_current_span("event.handle_pubsub") as span:
            try:
                channel = message["channel"]
                event_data = message["data"]

                # Extract event type from channel name
                event_type_str = channel.replace("events.", "")
                event_type = EventType(event_type_str)

                add_span_attributes(span,
                    event_type=event_type_str,
                    channel=channel
                )

                # Process event
                await self._process_event(event_type, event_data)

            except Exception as e:
                logger.error(f"Failed to handle pub/sub message: {e}")
                add_span_attributes(span, error=str(e))

    async def _process_event(self, event_type: EventType, event_data: str):
        """Process event with registered handlers"""
        if event_type not in self.handlers:
            return

        try:
            # Deserialize event
            event = self.schema_registry.deserialize_event(
                event_data, event_type, EventVersion.V1
            )

            # Call all registered handlers
            handlers = self.handlers[event_type]
            await asyncio.gather(
                *[self._call_handler(handler, event) for handler in handlers],
                return_exceptions=True
            )

        except Exception as e:
            logger.error(f"Failed to process event {event_type.value}: {e}")

    async def _call_handler(self, handler: EventHandler, event: BaseModel):
        """Call event handler safely"""
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)

        except Exception as e:
            logger.error(f"Event handler failed: {e}")

    async def replay_events(
        self,
        event_type: EventType,
        from_timestamp: Optional[datetime] = None,
        to_timestamp: Optional[datetime] = None,
        max_count: int = 1000
    ):
        """Replay events from stream"""
        if not self.is_connected:
            raise RuntimeError("Event subscriber not initialized")

        stream_name = f"events:{event_type.value}"

        try:
            # Read events from stream
            start_id = "0" if not from_timestamp else f"{int(from_timestamp.timestamp() * 1000)}-0"
            end_id = "+" if not to_timestamp else f"{int(to_timestamp.timestamp() * 1000)}-0"

            messages = await self.redis_client.xrange(
                stream_name, min=start_id, max=end_id, count=max_count
            )

            replayed = 0
            for msg_id, fields in messages:
                event_data = fields.get("event_data")
                if event_data:
                    await self._process_event(event_type, event_data)
                    replayed += 1

            logger.info(f"Replayed {replayed} events of type {event_type.value}")
            return replayed

        except Exception as e:
            logger.error(f"Failed to replay events: {e}")
            raise

    async def get_pending_messages(self) -> Dict[str, int]:
        """Get count of pending messages per stream"""
        if not self.is_connected:
            return {}

        pending_counts = {}
        for event_type in self.subscribed_events:
            stream_name = f"events:{event_type.value}"
            try:
                info = await self.redis_client.xpending_range(
                    stream_name, self.consumer_group, "-", "+", 1
                )
                pending_counts[event_type.value] = len(info)
            except Exception as e:
                logger.warning(f"Failed to get pending count for {stream_name}: {e}")
                pending_counts[event_type.value] = -1

        return pending_counts

    async def health_check(self) -> Dict[str, Any]:
        """Health check for event subscriber"""
        try:
            if not self.redis_client or not self.pubsub_client:
                return {"status": "unhealthy", "error": "Redis clients not initialized"}

            # Test connections
            await self.redis_client.ping()
            await self.pubsub_client.ping()

            pending = await self.get_pending_messages()

            return {
                "status": "healthy",
                "redis_connected": True,
                "subscribed_events": list(self.subscribed_events),
                "handler_count": sum(len(handlers) for handlers in self.handlers.values()),
                "pending_messages": pending,
                "consumer_group": self.consumer_group,
                "consumer_name": self.consumer_name
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "redis_connected": False
            }