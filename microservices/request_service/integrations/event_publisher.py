"""
Event Publisher for Analytics Service Integration

Task 2.2: Request Service Integration
Publishes request events to Redis Streams for Analytics Service
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
    - request.created
    - request.assigned
    - request.completed
    - request.cancelled
    """

    def __init__(self, redis_url: str = "redis://redis:6379/2"):
        """
        Initialize event publisher

        Args:
            redis_url: Redis connection URL
        """
        self.redis_url = redis_url
        self.stream_name = "analytics:events"
        self.service_name = "request-service"
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
            event_type: Type of event (e.g., 'request.created')
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

    async def publish_request_created(
        self,
        request_number: str,
        applicant_id: int,
        category: str,
        priority: str,
        location: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Publish request.created event

        Args:
            request_number: Request number (YYMMDD-NNN format)
            applicant_id: Applicant user ID
            category: Request category
            priority: Priority level
            location: Request location
            **kwargs: Additional fields
        """
        payload = {
            "request_number": request_number,
            "applicant_id": applicant_id,
            "category": category,
            "priority": priority,
            "location": location,
            **kwargs
        }

        return await self.publish_event("request.created", payload)

    async def publish_request_assigned(
        self,
        request_number: str,
        executor_id: int,
        assigned_by: int,
        **kwargs
    ) -> str:
        """
        Publish request.assigned event

        Args:
            request_number: Request number
            executor_id: Executor user ID
            assigned_by: User who assigned
            **kwargs: Additional fields
        """
        payload = {
            "request_number": request_number,
            "executor_id": executor_id,
            "assigned_by": assigned_by,
            **kwargs
        }

        return await self.publish_event("request.assigned", payload)

    async def publish_request_completed(
        self,
        request_number: str,
        executor_id: int,
        resolution_time_hours: Optional[float] = None,
        rating: Optional[float] = None,
        **kwargs
    ) -> str:
        """
        Publish request.completed event

        Args:
            request_number: Request number
            executor_id: Executor user ID
            resolution_time_hours: Time to resolve (hours)
            rating: Completion rating
            **kwargs: Additional fields
        """
        payload = {
            "request_number": request_number,
            "executor_id": executor_id,
            "resolution_time_hours": resolution_time_hours,
            "rating": rating,
            **kwargs
        }

        return await self.publish_event("request.completed", payload)

    async def publish_request_cancelled(
        self,
        request_number: str,
        cancelled_by: int,
        cancellation_reason: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Publish request.cancelled event

        Args:
            request_number: Request number
            cancelled_by: User who cancelled
            cancellation_reason: Reason for cancellation
            **kwargs: Additional fields
        """
        payload = {
            "request_number": request_number,
            "cancelled_by": cancelled_by,
            "cancellation_reason": cancellation_reason,
            **kwargs
        }

        return await self.publish_event("request.cancelled", payload)

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
