# Event Publisher
# UK Management Bot - Microservices Event Architecture

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
import redis.asyncio as redis
from pydantic import BaseModel

from config import settings
# from shared.events.schema_registry import EventType, EventVersion, BaseEvent, get_schema_registry
from middleware.tracing import get_tracer, add_span_attributes

logger = logging.getLogger(__name__)

class EventPublisher:
    """Redis-based event publisher with schema validation"""

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or settings.redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.is_connected = False
        self.schema_registry = get_schema_registry()
        self.tracer = get_tracer()

    async def initialize(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
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
            logger.error(f"Failed to initialize event publisher: {e}")
            self.is_connected = False
            raise

    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            self.is_connected = False
            logger.info("Event publisher closed")

    async def publish(
        self,
        event_type: EventType,
        event_data: Dict[str, Any],
        correlation_id: Optional[str] = None,
        version: EventVersion = EventVersion.V1
    ) -> str:
        """Publish event with schema validation"""
        if not self.is_connected or not self.redis_client:
            raise RuntimeError("Event publisher not initialized")

        # Generate event ID
        event_id = str(uuid.uuid4())

        # Create base event data
        base_event_data = {
            "event_id": event_id,
            "event_type": event_type.value,
            "version": version.value,
            "timestamp": datetime.utcnow(),
            "source_service": settings.service_name,
            "correlation_id": correlation_id,
            **event_data
        }

        with self.tracer.start_as_current_span("event.publish") as span:
            add_span_attributes(span,
                event_type=event_type.value,
                event_id=event_id,
                correlation_id=correlation_id
            )

            try:
                # Validate event against schema
                validated_event = self.schema_registry.validate_event(
                    event_type, base_event_data, version
                )

                # Serialize event
                event_json = self.schema_registry.serialize_event(validated_event)

                # Publish to Redis streams and pub/sub
                await asyncio.gather(
                    self._publish_to_stream(event_type, event_json, event_id),
                    self._publish_to_pubsub(event_type, event_json)
                )

                # Log successful publication
                logger.info(f"Published event {event_type.value} with ID {event_id}")
                add_span_attributes(span, published=True)

                return event_id

            except Exception as e:
                logger.error(f"Failed to publish event {event_type.value}: {e}")
                add_span_attributes(span, error=str(e), published=False)
                raise

    async def _publish_to_stream(
        self,
        event_type: EventType,
        event_json: str,
        event_id: str
    ):
        """Publish event to Redis stream for durability"""
        stream_name = f"events:{event_type.value}"

        try:
            await self.redis_client.xadd(
                stream_name,
                {
                    "event_id": event_id,
                    "event_data": event_json,
                    "timestamp": datetime.utcnow().isoformat()
                },
                maxlen=10000  # Keep last 10k events per stream
            )
            logger.debug(f"Published to stream {stream_name}")

        except Exception as e:
            logger.error(f"Failed to publish to stream {stream_name}: {e}")
            raise

    async def _publish_to_pubsub(
        self,
        event_type: EventType,
        event_json: str
    ):
        """Publish event to Redis pub/sub for real-time delivery"""
        channel_name = f"events.{event_type.value}"

        try:
            await self.redis_client.publish(channel_name, event_json)
            logger.debug(f"Published to channel {channel_name}")

        except Exception as e:
            logger.error(f"Failed to publish to channel {channel_name}: {e}")
            raise

    async def publish_batch(
        self,
        events: List[Dict[str, Any]],
        correlation_id: Optional[str] = None
    ) -> List[str]:
        """Publish multiple events in batch"""
        if not events:
            return []

        event_ids = []
        with self.tracer.start_as_current_span("event.publish_batch") as span:
            add_span_attributes(span,
                batch_size=len(events),
                correlation_id=correlation_id
            )

            try:
                # Use Redis pipeline for batch operations
                pipeline = self.redis_client.pipeline()

                for event in events:
                    event_type = EventType(event["event_type"])
                    event_id = await self._prepare_batch_event(
                        pipeline, event_type, event, correlation_id
                    )
                    event_ids.append(event_id)

                # Execute all operations
                await pipeline.execute()

                logger.info(f"Published batch of {len(events)} events")
                add_span_attributes(span, published=True, event_count=len(events))

                return event_ids

            except Exception as e:
                logger.error(f"Failed to publish event batch: {e}")
                add_span_attributes(span, error=str(e), published=False)
                raise

    async def _prepare_batch_event(
        self,
        pipeline,
        event_type: EventType,
        event_data: Dict[str, Any],
        correlation_id: Optional[str]
    ) -> str:
        """Prepare single event for batch publication"""
        event_id = str(uuid.uuid4())

        base_event_data = {
            "event_id": event_id,
            "event_type": event_type.value,
            "version": EventVersion.V1.value,
            "timestamp": datetime.utcnow(),
            "source_service": settings.service_name,
            "correlation_id": correlation_id,
            **event_data
        }

        # Validate and serialize
        validated_event = self.schema_registry.validate_event(
            event_type, base_event_data, EventVersion.V1
        )
        event_json = self.schema_registry.serialize_event(validated_event)

        # Add to pipeline
        stream_name = f"events:{event_type.value}"
        channel_name = f"events.{event_type.value}"

        pipeline.xadd(
            stream_name,
            {
                "event_id": event_id,
                "event_data": event_json,
                "timestamp": datetime.utcnow().isoformat()
            },
            maxlen=10000
        )
        pipeline.publish(channel_name, event_json)

        return event_id

    async def get_stream_info(self, event_type: EventType) -> Dict[str, Any]:
        """Get information about event stream"""
        if not self.is_connected or not self.redis_client:
            raise RuntimeError("Event publisher not initialized")

        stream_name = f"events:{event_type.value}"
        try:
            info = await self.redis_client.xinfo_stream(stream_name)
            return {
                "stream": stream_name,
                "length": info.get("length", 0),
                "first_entry": info.get("first-entry"),
                "last_entry": info.get("last-entry"),
                "consumers": info.get("groups", 0)
            }
        except Exception as e:
            logger.error(f"Failed to get stream info for {stream_name}: {e}")
            return {"error": str(e)}

    async def health_check(self) -> Dict[str, Any]:
        """Health check for event publisher"""
        try:
            if not self.redis_client:
                return {"status": "unhealthy", "error": "Redis client not initialized"}

            # Test Redis connection
            await self.redis_client.ping()

            return {
                "status": "healthy",
                "redis_connected": True,
                "schema_registry_loaded": len(self.schema_registry.get_supported_events()) > 0
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "redis_connected": False
            }