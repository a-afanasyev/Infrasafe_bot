"""
Event Schemas - Pydantic models for event validation

Task 1.2: Core Data Models - Pydantic schemas
"""

from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class EventBase(BaseModel):
    """Base event schema"""
    event_type: str = Field(..., description="Type of event (e.g., shift.created)")
    service_name: str = Field(..., description="Source service name")
    service_version: Optional[str] = Field(None, description="Service version")
    payload: Dict[str, Any] = Field(..., description="Event data payload")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class EventCreate(EventBase):
    """Schema for creating new event"""
    event_id: str = Field(..., description="Unique event ID")


class EventResponse(EventBase):
    """Schema for event response"""
    id: int
    event_id: str
    status: str
    created_at: datetime
    processed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0

    class Config:
        from_attributes = True


class EventUpdate(BaseModel):
    """Schema for updating event status"""
    status: Optional[str] = None
    processed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: Optional[int] = None
