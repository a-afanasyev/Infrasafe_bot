"""
Event Publisher for Analytics Service Integration

Task 2.1: Shift Service Integration
Publishes shift events to Redis Streams for Analytics Service
"""

import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import uuid4

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class EventPublisher:
    """
    Publishes events to Redis Streams for Analytics Service

    Events published:
    - shift.created
    - shift.completed
    - shift.cancelled
    - shift.updated
    - shift.assigned
    """

    def __init__(self, redis_url: str = "redis://redis:6379/2"):
        """
        Initialize event publisher

        Args:
            redis_url: Redis connection URL
        """
        self.redis_url = redis_url
        self.stream_name = "analytics:events"
        self.service_name = "shift-service"
        self.service_version = "1.0.0"
        self._client: Optional[redis.Redis] = None

    async def _get_client(self) -> redis.Redis:
        """Get or create Redis client"""
        if self._client is None:
            self._client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
        return self._client

    async def publish_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Publish event to Redis Stream

        Args:
            event_type: Type of event (e.g., 'shift.created')
            payload: Event data payload
            metadata: Additional metadata

        Returns:
            Event ID
        """
        try:
            client = await self._get_client()

            # Generate event ID
            event_id = f"{self.service_name}-{event_type}-{uuid4().hex[:8]}"

            # Prepare event data
            event_data = {
                "event_id": event_id,
                "event_type": event_type,
                "service_name": self.service_name,
                "service_version": self.service_version,
                "payload": json.dumps(payload, default=str),
                "metadata": json.dumps(metadata or {}, default=str),
                "timestamp": datetime.utcnow().isoformat()
            }

            # Publish to stream
            message_id = await client.xadd(self.stream_name, event_data)

            logger.debug(
                f"📤 Event published: {event_type} (id: {event_id}, message_id: {message_id})"
            )

            return event_id

        except Exception as e:
            logger.error(f"Failed to publish event {event_type}: {e}", exc_info=True)
            # Don't raise - publishing failure shouldn't break main flow
            return ""

    async def publish_shift_created(
        self,
        shift_id: int,
        shift_number: str,
        executor_id: int,
        specialization: str,
        start_time: datetime,
        end_time: datetime,
        **kwargs
    ) -> str:
        """
        Publish shift.created event

        Args:
            shift_id: Shift ID
            shift_number: Shift number (e.g., '2025-10-06-001')
            executor_id: Executor user ID
            specialization: Specialization type
            start_time: Shift start time
            end_time: Shift end time
            **kwargs: Additional fields
        """
        payload = {
            "shift_id": shift_id,
            "shift_number": shift_number,
            "executor_id": executor_id,
            "specialization": specialization,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_hours": (end_time - start_time).total_seconds() / 3600,
            **kwargs
        }

        return await self.publish_event("shift.created", payload)

    async def publish_shift_completed(
        self,
        shift_id: int,
        shift_number: str,
        executor_id: int,
        completion_rating: Optional[float] = None,
        efficiency_score: Optional[float] = None,
        **kwargs
    ) -> str:
        """
        Publish shift.completed event

        Args:
            shift_id: Shift ID
            shift_number: Shift number
            executor_id: Executor user ID
            completion_rating: Completion rating (1-5)
            efficiency_score: Efficiency score (0-100)
            **kwargs: Additional fields
        """
        payload = {
            "shift_id": shift_id,
            "shift_number": shift_number,
            "executor_id": executor_id,
            "completion_rating": completion_rating,
            "efficiency_score": efficiency_score,
            **kwargs
        }

        return await self.publish_event("shift.completed", payload)

    async def publish_shift_cancelled(
        self,
        shift_id: int,
        shift_number: str,
        executor_id: int,
        cancellation_reason: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Publish shift.cancelled event

        Args:
            shift_id: Shift ID
            shift_number: Shift number
            executor_id: Executor user ID
            cancellation_reason: Reason for cancellation
            **kwargs: Additional fields
        """
        payload = {
            "shift_id": shift_id,
            "shift_number": shift_number,
            "executor_id": executor_id,
            "cancellation_reason": cancellation_reason,
            **kwargs
        }

        return await self.publish_event("shift.cancelled", payload)

    async def publish_shift_assigned(
        self,
        shift_id: int,
        shift_number: str,
        executor_id: int,
        request_id: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Publish shift.assigned event (shift assigned to request)

        Args:
            shift_id: Shift ID
            shift_number: Shift number
            executor_id: Executor user ID
            request_id: Request number assigned to
            **kwargs: Additional fields
        """
        payload = {
            "shift_id": shift_id,
            "shift_number": shift_number,
            "executor_id": executor_id,
            "request_id": request_id,
            **kwargs
        }

        return await self.publish_event("shift.assigned", payload)

    async def close(self) -> None:
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._client = None


# Global instance
_event_publisher: Optional[EventPublisher] = None


def get_event_publisher() -> EventPublisher:
    """Get global event publisher instance"""
    global _event_publisher
    if _event_publisher is None:
        _event_publisher = EventPublisher()
    return _event_publisher
