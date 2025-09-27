# Event Schema Registry
# UK Management Bot - Microservices Event Architecture

import json
import logging
from typing import Dict, Any, Optional, Type
from datetime import datetime
from pydantic import BaseModel, ValidationError
from enum import Enum

logger = logging.getLogger(__name__)

class EventVersion(str, Enum):
    """Event schema versions"""
    V1 = "v1"
    V2 = "v2"

class EventType(str, Enum):
    """Event types in the system"""
    # User events
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    USER_VERIFIED = "user.verified"

    # Request events
    REQUEST_CREATED = "request.created"
    REQUEST_UPDATED = "request.updated"
    REQUEST_ASSIGNED = "request.assigned"
    REQUEST_COMPLETED = "request.completed"
    REQUEST_CANCELLED = "request.cancelled"

    # Assignment events
    ASSIGNMENT_CREATED = "assignment.created"
    ASSIGNMENT_ACCEPTED = "assignment.accepted"
    ASSIGNMENT_REJECTED = "assignment.rejected"
    ASSIGNMENT_COMPLETED = "assignment.completed"

    # Shift events
    SHIFT_CREATED = "shift.created"
    SHIFT_UPDATED = "shift.updated"
    SHIFT_ASSIGNED = "shift.assigned"
    SHIFT_TRANSFERRED = "shift.transferred"

    # Notification events
    NOTIFICATION_SEND = "notification.send"
    NOTIFICATION_DELIVERED = "notification.delivered"
    NOTIFICATION_FAILED = "notification.failed"

    # System events
    SYSTEM_HEALTH_CHECK = "system.health_check"
    SYSTEM_ERROR = "system.error"

class BaseEvent(BaseModel):
    """Base event schema"""
    event_id: str
    event_type: EventType
    version: EventVersion
    timestamp: datetime
    source_service: str
    correlation_id: Optional[str] = None
    user_id: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class EventSchemaRegistry:
    """Registry for event schemas with versioning support"""

    def __init__(self):
        self._schemas: Dict[str, Dict[EventVersion, Type[BaseModel]]] = {}
        self._register_default_schemas()

    def _register_default_schemas(self):
        """Register default event schemas"""
        from .contracts import (
            UserCreatedEventV1, UserUpdatedEventV1,
            RequestCreatedEventV1, RequestAssignedEventV1,
            AssignmentCreatedEventV1, ShiftCreatedEventV1,
            NotificationSendEventV1
        )

        # User events
        self.register_schema(EventType.USER_CREATED, EventVersion.V1, UserCreatedEventV1)
        self.register_schema(EventType.USER_UPDATED, EventVersion.V1, UserUpdatedEventV1)

        # Request events
        self.register_schema(EventType.REQUEST_CREATED, EventVersion.V1, RequestCreatedEventV1)
        self.register_schema(EventType.REQUEST_ASSIGNED, EventVersion.V1, RequestAssignedEventV1)

        # Assignment events
        self.register_schema(EventType.ASSIGNMENT_CREATED, EventVersion.V1, AssignmentCreatedEventV1)

        # Shift events
        self.register_schema(EventType.SHIFT_CREATED, EventVersion.V1, ShiftCreatedEventV1)

        # Notification events
        self.register_schema(EventType.NOTIFICATION_SEND, EventVersion.V1, NotificationSendEventV1)

    def register_schema(
        self,
        event_type: EventType,
        version: EventVersion,
        schema_class: Type[BaseModel]
    ):
        """Register event schema for specific type and version"""
        event_key = event_type.value
        if event_key not in self._schemas:
            self._schemas[event_key] = {}

        self._schemas[event_key][version] = schema_class
        logger.info(f"Registered schema for {event_type.value} {version.value}")

    def get_schema(
        self,
        event_type: EventType,
        version: EventVersion = EventVersion.V1
    ) -> Optional[Type[BaseModel]]:
        """Get event schema by type and version"""
        event_key = event_type.value
        return self._schemas.get(event_key, {}).get(version)

    def validate_event(
        self,
        event_type: EventType,
        event_data: Dict[str, Any],
        version: EventVersion = EventVersion.V1
    ) -> BaseModel:
        """Validate event data against schema"""
        schema_class = self.get_schema(event_type, version)

        if not schema_class:
            raise ValueError(f"No schema found for {event_type.value} {version.value}")

        try:
            return schema_class(**event_data)
        except ValidationError as e:
            logger.error(f"Event validation failed for {event_type.value}: {e}")
            raise ValueError(f"Event validation failed: {e}")

    def serialize_event(self, event: BaseModel) -> str:
        """Serialize event to JSON string"""
        try:
            return event.model_dump_json()
        except Exception as e:
            logger.error(f"Event serialization failed: {e}")
            raise ValueError(f"Event serialization failed: {e}")

    def deserialize_event(
        self,
        event_data: str,
        event_type: EventType,
        version: EventVersion = EventVersion.V1
    ) -> BaseModel:
        """Deserialize JSON string to event object"""
        try:
            data = json.loads(event_data)
            return self.validate_event(event_type, data, version)
        except json.JSONDecodeError as e:
            logger.error(f"Event deserialization failed: {e}")
            raise ValueError(f"Event deserialization failed: {e}")

    def get_supported_events(self) -> Dict[str, list]:
        """Get list of supported event types and versions"""
        result = {}
        for event_type, versions in self._schemas.items():
            result[event_type] = list(versions.keys())
        return result

    def migrate_event(
        self,
        event: BaseModel,
        target_version: EventVersion
    ) -> BaseModel:
        """Migrate event from one version to another"""
        # This is a placeholder for event migration logic
        # In a real implementation, you would define migration rules
        # between different versions of the same event type

        current_event_type = getattr(event, 'event_type', None)
        if not current_event_type:
            raise ValueError("Event missing event_type field")

        target_schema = self.get_schema(EventType(current_event_type), target_version)
        if not target_schema:
            raise ValueError(f"No target schema found for {current_event_type} {target_version}")

        # Simple migration - just re-validate with target schema
        # In practice, you'd have more sophisticated migration logic
        try:
            event_dict = event.model_dump()
            return target_schema(**event_dict)
        except ValidationError as e:
            logger.error(f"Event migration failed: {e}")
            raise ValueError(f"Event migration failed: {e}")

# Global schema registry instance
registry = EventSchemaRegistry()

def get_schema_registry() -> EventSchemaRegistry:
    """Get global schema registry instance"""
    return registry