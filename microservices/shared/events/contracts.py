# Event Contracts
# UK Management Bot - Microservices Event Architecture

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from .schema_registry import BaseEvent, EventType, EventVersion

# User Events

class UserCreatedEventV1(BaseEvent):
    """User created event - Version 1"""
    event_type: EventType = Field(default=EventType.USER_CREATED, const=True)
    version: EventVersion = Field(default=EventVersion.V1, const=True)

    # Event payload
    user_id: int
    telegram_id: int
    username: Optional[str] = None
    first_name: str
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    role: str
    specializations: Optional[List[str]] = None
    is_verified: bool = False

class UserUpdatedEventV1(BaseEvent):
    """User updated event - Version 1"""
    event_type: EventType = Field(default=EventType.USER_UPDATED, const=True)
    version: EventVersion = Field(default=EventVersion.V1, const=True)

    # Event payload
    user_id: int
    changed_fields: List[str]
    old_values: Dict[str, Any]
    new_values: Dict[str, Any]

class UserVerifiedEventV1(BaseEvent):
    """User verified event - Version 1"""
    event_type: EventType = Field(default=EventType.USER_VERIFIED, const=True)
    version: EventVersion = Field(default=EventVersion.V1, const=True)

    # Event payload
    user_id: int
    verified_by: int
    verification_documents: List[str]

# Request Events

class RequestCreatedEventV1(BaseEvent):
    """Request created event - Version 1"""
    event_type: EventType = Field(default=EventType.REQUEST_CREATED, const=True)
    version: EventVersion = Field(default=EventVersion.V1, const=True)

    # Event payload
    request_number: str  # YYMMDD-NNN format
    creator_id: int
    description: str
    location: str
    urgency: str  # low, medium, high, critical
    specialization_required: Optional[str] = None
    estimated_duration: Optional[int] = None  # minutes
    photos: Optional[List[str]] = None

class RequestUpdatedEventV1(BaseEvent):
    """Request updated event - Version 1"""
    event_type: EventType = Field(default=EventType.REQUEST_UPDATED, const=True)
    version: EventVersion = Field(default=EventVersion.V1, const=True)

    # Event payload
    request_number: str
    changed_fields: List[str]
    old_values: Dict[str, Any]
    new_values: Dict[str, Any]
    updated_by: int

class RequestAssignedEventV1(BaseEvent):
    """Request assigned event - Version 1"""
    event_type: EventType = Field(default=EventType.REQUEST_ASSIGNED, const=True)
    version: EventVersion = Field(default=EventVersion.V1, const=True)

    # Event payload
    request_number: str
    executor_id: int
    assigned_by: int
    assignment_method: str  # manual, auto, ai
    estimated_completion: Optional[datetime] = None
    priority_score: Optional[float] = None

class RequestCompletedEventV1(BaseEvent):
    """Request completed event - Version 1"""
    event_type: EventType = Field(default=EventType.REQUEST_COMPLETED, const=True)
    version: EventVersion = Field(default=EventVersion.V1, const=True)

    # Event payload
    request_number: str
    executor_id: int
    completion_time: datetime
    actual_duration: int  # minutes
    quality_rating: Optional[int] = None  # 1-5
    completion_photos: Optional[List[str]] = None
    materials_used: Optional[Dict[str, Any]] = None

# Assignment Events

class AssignmentCreatedEventV1(BaseEvent):
    """Assignment created event - Version 1"""
    event_type: EventType = Field(default=EventType.ASSIGNMENT_CREATED, const=True)
    version: EventVersion = Field(default=EventVersion.V1, const=True)

    # Event payload
    assignment_id: int
    request_number: str
    executor_id: int
    assigned_by: int
    assignment_type: str  # individual, group
    deadline: Optional[datetime] = None

class AssignmentAcceptedEventV1(BaseEvent):
    """Assignment accepted event - Version 1"""
    event_type: EventType = Field(default=EventType.ASSIGNMENT_ACCEPTED, const=True)
    version: EventVersion = Field(default=EventVersion.V1, const=True)

    # Event payload
    assignment_id: int
    request_number: str
    executor_id: int
    accepted_at: datetime
    estimated_start: Optional[datetime] = None

class AssignmentRejectedEventV1(BaseEvent):
    """Assignment rejected event - Version 1"""
    event_type: EventType = Field(default=EventType.ASSIGNMENT_REJECTED, const=True)
    version: EventVersion = Field(default=EventVersion.V1, const=True)

    # Event payload
    assignment_id: int
    request_number: str
    executor_id: int
    rejected_at: datetime
    reason: Optional[str] = None

# Shift Events

class ShiftCreatedEventV1(BaseEvent):
    """Shift created event - Version 1"""
    event_type: EventType = Field(default=EventType.SHIFT_CREATED, const=True)
    version: EventVersion = Field(default=EventVersion.V1, const=True)

    # Event payload
    shift_id: int
    executor_id: int
    date: datetime
    start_time: datetime
    end_time: datetime
    specialization: str
    template_id: Optional[int] = None
    created_by: Optional[int] = None

class ShiftTransferredEventV1(BaseEvent):
    """Shift transferred event - Version 1"""
    event_type: EventType = Field(default=EventType.SHIFT_TRANSFERRED, const=True)
    version: EventVersion = Field(default=EventVersion.V1, const=True)

    # Event payload
    shift_id: int
    from_executor_id: int
    to_executor_id: int
    transfer_reason: str
    approved_by: Optional[int] = None
    transfer_date: datetime

# Notification Events

class NotificationSendEventV1(BaseEvent):
    """Notification send event - Version 1"""
    event_type: EventType = Field(default=EventType.NOTIFICATION_SEND, const=True)
    version: EventVersion = Field(default=EventVersion.V1, const=True)

    # Event payload
    recipient_id: int
    message: str
    notification_type: str  # telegram, email, sms
    channel: str
    priority: str  # low, normal, high
    template_id: Optional[str] = None
    template_data: Optional[Dict[str, Any]] = None

class NotificationDeliveredEventV1(BaseEvent):
    """Notification delivered event - Version 1"""
    event_type: EventType = Field(default=EventType.NOTIFICATION_DELIVERED, const=True)
    version: EventVersion = Field(default=EventVersion.V1, const=True)

    # Event payload
    recipient_id: int
    notification_id: str
    channel: str
    delivered_at: datetime
    delivery_status: str  # delivered, read, failed

# System Events

class SystemHealthCheckEventV1(BaseEvent):
    """System health check event - Version 1"""
    event_type: EventType = Field(default=EventType.SYSTEM_HEALTH_CHECK, const=True)
    version: EventVersion = Field(default=EventVersion.V1, const=True)

    # Event payload
    service_name: str
    health_status: str  # healthy, degraded, unhealthy
    check_results: Dict[str, Any]
    response_time_ms: float
    uptime_seconds: int

class SystemErrorEventV1(BaseEvent):
    """System error event - Version 1"""
    event_type: EventType = Field(default=EventType.SYSTEM_ERROR, const=True)
    version: EventVersion = Field(default=EventVersion.V1, const=True)

    # Event payload
    service_name: str
    error_type: str
    error_message: str
    error_code: Optional[str] = None
    stack_trace: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    severity: str  # low, medium, high, critical