"""
Integration Service - Event Schemas
UK Management Bot

Event schemas for Integration Service events published to message bus.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field


class IntegrationEventBase(BaseModel):
    """Base class for all integration events"""
    event_id: UUID = Field(description="Unique event ID")
    event_type: str = Field(description="Event type")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Event timestamp")
    management_company_id: str = Field(description="Tenant ID")
    service_name: str = Field(description="Service that generated the event")
    correlation_id: Optional[str] = Field(None, description="Correlation ID for tracking")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


# 1. integration.service.registered
class IntegrationServiceRegisteredEvent(IntegrationEventBase):
    """
    Event: External service registered/configured

    Published when: New external service added to Integration Service
    Subscribers: Analytics Service, Notification Service
    """
    event_type: str = "integration.service.registered"
    service_id: UUID = Field(description="External service ID")
    service_type: str = Field(description="Service type: geocoding, sheets, maps, webhook")
    display_name: str = Field(description="Human-readable service name")
    is_active: bool = Field(description="Service active status")
    priority: int = Field(description="Service priority")
    created_by: Optional[UUID] = Field(None, description="User who registered the service")


# 2. integration.request.sent
class IntegrationRequestSentEvent(IntegrationEventBase):
    """
    Event: External API request sent

    Published when: Request sent to external service
    Subscribers: Analytics Service, Logging Service
    """
    event_type: str = "integration.request.sent"
    log_id: UUID = Field(description="Integration log ID")
    service_id: Optional[UUID] = Field(None, description="External service ID")
    operation: str = Field(description="Operation: geocode, sheets_read, etc.")
    endpoint: Optional[str] = Field(None, description="API endpoint")
    http_method: Optional[str] = Field(None, description="HTTP method")
    request_id: Optional[str] = Field(None, description="Request ID for tracing")
    user_id: Optional[UUID] = Field(None, description="User who initiated request")
    source_service: Optional[str] = Field(None, description="Originating service")


# 3. integration.request.completed
class IntegrationRequestCompletedEvent(IntegrationEventBase):
    """
    Event: External API request completed successfully

    Published when: Request completed with success status
    Subscribers: Analytics Service, Cache Service, Logging Service
    """
    event_type: str = "integration.request.completed"
    log_id: UUID = Field(description="Integration log ID")
    service_id: Optional[UUID] = Field(None, description="External service ID")
    operation: str = Field(description="Operation")
    response_status_code: int = Field(description="HTTP status code")
    duration_ms: int = Field(description="Request duration in milliseconds")
    response_size_bytes: Optional[int] = Field(None, description="Response size")
    request_id: Optional[str] = Field(None, description="Request ID for tracing")
    estimated_cost: Optional[float] = Field(None, description="API call cost")
    cached: bool = Field(default=False, description="Response was cached")


# 4. integration.request.failed
class IntegrationRequestFailedEvent(IntegrationEventBase):
    """
    Event: External API request failed

    Published when: Request failed with error
    Subscribers: Analytics Service, Notification Service, Alert Service
    """
    event_type: str = "integration.request.failed"
    log_id: UUID = Field(description="Integration log ID")
    service_id: Optional[UUID] = Field(None, description="External service ID")
    operation: str = Field(description="Operation")
    error_message: str = Field(description="Error message")
    error_code: Optional[str] = Field(None, description="Error code")
    response_status_code: Optional[int] = Field(None, description="HTTP status code if available")
    duration_ms: Optional[int] = Field(None, description="Request duration before failure")
    retry_count: int = Field(default=0, description="Number of retries attempted")
    request_id: Optional[str] = Field(None, description="Request ID for tracing")
    will_retry: bool = Field(default=False, description="Will attempt retry")


# 5. integration.webhook.received
class IntegrationWebhookReceivedEvent(IntegrationEventBase):
    """
    Event: Webhook received from external service

    Published when: Incoming webhook received
    Subscribers: Target services, Analytics Service
    """
    event_type: str = "integration.webhook.received"
    webhook_id: UUID = Field(description="Webhook config ID")
    webhook_name: str = Field(description="Webhook name")
    source_service: str = Field(description="External service that sent webhook")
    webhook_event_type: str = Field(description="Webhook event type from source")
    payload_size_bytes: int = Field(description="Webhook payload size")
    signature_verified: bool = Field(description="Signature verification result")
    target_queue: Optional[str] = Field(None, description="Message queue for processing")
    target_service: Optional[str] = Field(None, description="Target service for routing")


# 6. integration.rate_limit.exceeded
class IntegrationRateLimitExceededEvent(IntegrationEventBase):
    """
    Event: API rate limit exceeded

    Published when: Rate limit threshold exceeded
    Subscribers: Alert Service, Analytics Service, Notification Service
    """
    event_type: str = "integration.rate_limit.exceeded"
    service_id: UUID = Field(description="External service ID")
    window_type: str = Field(description="Window type: minute, hour, day")
    max_requests: int = Field(description="Maximum requests allowed")
    current_requests: int = Field(description="Current request count")
    utilization_percent: float = Field(description="Rate limit utilization percentage")
    rate_limit_reset_at: Optional[datetime] = Field(None, description="When rate limit resets")
    blocked_operations: List[str] = Field(default_factory=list, description="Operations that were blocked")


# 7. integration.cache.hit
class IntegrationCacheHitEvent(IntegrationEventBase):
    """
    Event: Cache hit for integration request

    Published when: Cached response returned
    Subscribers: Analytics Service
    """
    event_type: str = "integration.cache.hit"
    cache_id: UUID = Field(description="Cache entry ID")
    cache_key: str = Field(description="Cache key")
    operation: str = Field(description="Operation")
    cache_age_seconds: int = Field(description="Age of cached data in seconds")
    remaining_ttl_seconds: int = Field(description="Remaining TTL")
    hit_count: int = Field(description="Total hit count for this cache entry")


# 8. integration.cache.miss
class IntegrationCacheMissEvent(IntegrationEventBase):
    """
    Event: Cache miss for integration request

    Published when: Cache lookup failed, need to fetch from API
    Subscribers: Analytics Service
    """
    event_type: str = "integration.cache.miss"
    cache_key: str = Field(description="Cache key")
    operation: str = Field(description="Operation")
    will_populate: bool = Field(description="Will populate cache after fetch")


# 9. integration.health.degraded
class IntegrationHealthDegradedEvent(IntegrationEventBase):
    """
    Event: External service health degraded

    Published when: Service health check fails or performance degrades
    Subscribers: Alert Service, Notification Service, Analytics Service
    """
    event_type: str = "integration.health.degraded"
    service_id: UUID = Field(description="External service ID")
    health_status: str = Field(description="Health status: degraded, down")
    previous_status: str = Field(description="Previous health status")
    error_rate_percent: Optional[float] = Field(None, description="Error rate percentage")
    avg_response_time_ms: Optional[int] = Field(None, description="Average response time")
    consecutive_failures: int = Field(description="Consecutive failure count")
    fallback_service_id: Optional[UUID] = Field(None, description="Fallback service if configured")


# 10. integration.health.recovered
class IntegrationHealthRecoveredEvent(IntegrationEventBase):
    """
    Event: External service health recovered

    Published when: Service health returns to normal
    Subscribers: Notification Service, Analytics Service
    """
    event_type: str = "integration.health.recovered"
    service_id: UUID = Field(description="External service ID")
    health_status: str = Field(description="Health status: healthy")
    previous_status: str = Field(description="Previous health status")
    downtime_seconds: Optional[int] = Field(None, description="Total downtime duration")
    recovery_timestamp: datetime = Field(description="Recovery timestamp")


# Event Type Registry
EVENT_TYPE_MAP = {
    "integration.service.registered": IntegrationServiceRegisteredEvent,
    "integration.request.sent": IntegrationRequestSentEvent,
    "integration.request.completed": IntegrationRequestCompletedEvent,
    "integration.request.failed": IntegrationRequestFailedEvent,
    "integration.webhook.received": IntegrationWebhookReceivedEvent,
    "integration.rate_limit.exceeded": IntegrationRateLimitExceededEvent,
    "integration.cache.hit": IntegrationCacheHitEvent,
    "integration.cache.miss": IntegrationCacheMissEvent,
    "integration.health.degraded": IntegrationHealthDegradedEvent,
    "integration.health.recovered": IntegrationHealthRecoveredEvent,
}


def get_event_class(event_type: str):
    """Get event class by event type"""
    return EVENT_TYPE_MAP.get(event_type, IntegrationEventBase)
