# Shift Schemas for Shift Service
# UK Management Bot - Shift Service

from datetime import datetime, time
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, field_validator

from models.shifts import ShiftStatus, ShiftType, SpecializationType
from .common import CoordinatesSchema, PaginatedResponse


class ShiftCreate(BaseModel):
    """Schema for creating a new shift"""
    title: str = Field(..., min_length=1, max_length=200, description="Shift title")
    description: Optional[str] = Field(default=None, description="Shift description")

    start_time: datetime = Field(..., description="Shift start time (UTC)")
    end_time: datetime = Field(..., description="Shift end time (UTC)")

    specialization: SpecializationType = Field(..., description="Required specialization")
    shift_type: ShiftType = Field(default=ShiftType.REGULAR, description="Shift type")

    location: Optional[str] = Field(default=None, max_length=300, description="Location name")
    coordinates: Optional[CoordinatesSchema] = Field(default=None, description="GPS coordinates")
    address: Optional[str] = Field(default=None, description="Full address")

    requirements: Optional[Dict[str, Any]] = Field(default=None, description="Special requirements")
    priority: int = Field(default=1, ge=1, le=4, description="Priority level (1-4)")

    executor_id: Optional[UUID] = Field(default=None, description="Pre-assigned executor")
    template_id: Optional[UUID] = Field(default=None, description="Template reference")

    # Enhanced planning fields
    planned_start_time: Optional[datetime] = Field(default=None, description="Planned start time")
    planned_end_time: Optional[datetime] = Field(default=None, description="Planned end time")
    specialization_focus: Optional[List[str]] = Field(default=None, description="Specialization focus areas")
    coverage_areas: Optional[List[str]] = Field(default=None, description="Coverage geographic areas")
    geographic_zone: Optional[str] = Field(default=None, max_length=100, description="Geographic zone")

    # Workload management fields
    max_requests: Optional[int] = Field(default=10, ge=1, le=100, description="Maximum requests per shift")

    @field_validator('end_time')
    @classmethod
    def validate_end_time(cls, v, info):
        # Allow overnight shifts (e.g., 22:00-06:00)
        # Duration calculation in service handles this correctly
        return v

    model_config = ConfigDict(from_attributes=True)


class ShiftUpdate(BaseModel):
    """Schema for updating an existing shift"""
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None)

    start_time: Optional[datetime] = Field(default=None)
    end_time: Optional[datetime] = Field(default=None)

    status: Optional[ShiftStatus] = Field(default=None)
    shift_type: Optional[ShiftType] = Field(default=None)
    specialization: Optional[SpecializationType] = Field(default=None)

    location: Optional[str] = Field(default=None, max_length=300)
    coordinates: Optional[CoordinatesSchema] = Field(default=None)
    address: Optional[str] = Field(default=None)

    requirements: Optional[Dict[str, Any]] = Field(default=None)
    priority: Optional[int] = Field(default=None, ge=1, le=4)

    executor_id: Optional[UUID] = Field(default=None)

    # Enhanced planning fields
    planned_start_time: Optional[datetime] = Field(default=None)
    planned_end_time: Optional[datetime] = Field(default=None)
    specialization_focus: Optional[List[str]] = Field(default=None)
    coverage_areas: Optional[List[str]] = Field(default=None)
    geographic_zone: Optional[str] = Field(default=None, max_length=100)

    # Workload management fields
    max_requests: Optional[int] = Field(default=None, ge=1, le=100)

    model_config = ConfigDict(from_attributes=True)


class ShiftResponse(BaseModel):
    """Schema for shift response"""
    id: UUID = Field(description="Shift ID")
    title: str = Field(description="Shift title")
    description: Optional[str] = Field(description="Shift description")

    start_time: datetime = Field(description="Shift start time")
    end_time: datetime = Field(description="Shift end time")
    duration_hours: float = Field(description="Shift duration in hours")

    status: ShiftStatus = Field(description="Current status")
    shift_type: ShiftType = Field(description="Shift type")
    specialization: SpecializationType = Field(description="Required specialization")

    executor_id: Optional[UUID] = Field(description="Assigned executor")

    location: Optional[str] = Field(description="Location name")
    coordinates: Optional[Dict[str, float]] = Field(description="GPS coordinates")
    address: Optional[str] = Field(description="Full address")

    requirements: Optional[Dict[str, Any]] = Field(description="Special requirements")
    priority: int = Field(description="Priority level")

    template_id: Optional[UUID] = Field(description="Template reference")

    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")
    created_by: UUID = Field(description="Creator user ID")

    # Performance metrics
    completion_rating: Optional[float] = Field(description="Completion rating (1-5)")
    completion_notes: Optional[str] = Field(default=None, description="Completion notes (Bug #18 fix)")
    actual_duration_hours: Optional[float] = Field(description="Actual duration")
    efficiency_score: Optional[float] = Field(description="Efficiency score")

    # Enhanced planning fields
    planned_start_time: Optional[datetime] = Field(default=None, description="Planned start time")
    planned_end_time: Optional[datetime] = Field(default=None, description="Planned end time")
    specialization_focus: Optional[List[str]] = Field(default=None, description="Specialization focus areas")
    coverage_areas: Optional[List[str]] = Field(default=None, description="Coverage geographic areas")
    geographic_zone: Optional[str] = Field(default=None, description="Geographic zone")

    # Workload management fields (read-only in response)
    max_requests: int = Field(default=10, description="Maximum requests per shift")
    current_request_count: int = Field(default=0, description="Current number of requests")
    completed_requests: int = Field(default=0, description="Number of completed requests")
    average_completion_time: Optional[float] = Field(default=None, description="Average completion time")
    average_response_time: Optional[float] = Field(default=None, description="Average response time")

    model_config = ConfigDict(from_attributes=True)


class ShiftListResponse(BaseModel):
    """Paginated shift list response"""
    items: List[ShiftResponse] = Field(description="List of shifts")
    total: int = Field(description="Total number of shifts")
    page: int = Field(description="Current page number")
    size: int = Field(description="Items per page")
    pages: int = Field(description="Total number of pages")

    model_config = ConfigDict(from_attributes=True)


class ShiftTemplateCreate(BaseModel):
    """Schema for creating a shift template"""
    name: str = Field(..., min_length=1, max_length=200, description="Template name")
    description: Optional[str] = Field(default=None, description="Template description")

    start_time: time = Field(..., description="Template start time")
    end_time: time = Field(..., description="Template end time")

    days_of_week: List[int] = Field(..., description="Days of week (1=Monday, 7=Sunday)")
    specialization: SpecializationType = Field(..., description="Required specialization")
    max_executors: int = Field(default=1, ge=1, description="Maximum executors")

    auto_assign: bool = Field(default=False, description="Enable auto-assignment")
    recurrence_pattern: Optional[Dict[str, Any]] = Field(default=None, description="Recurrence rules")

    @field_validator('days_of_week')
    @classmethod
    def validate_days_of_week(cls, v):
        if not v or not all(1 <= day <= 7 for day in v):
            raise ValueError('days_of_week must contain values between 1 and 7')
        return sorted(list(set(v)))

    @field_validator('end_time')
    @classmethod
    def validate_end_time(cls, v, info):
        # Allow overnight shifts (e.g., 22:00-06:00)
        # Duration calculation in service handles this correctly
        return v

    model_config = ConfigDict(from_attributes=True)


class ShiftTemplateResponse(BaseModel):
    """Schema for shift template response"""
    id: UUID = Field(description="Template ID")
    name: str = Field(description="Template name")
    description: Optional[str] = Field(description="Template description")

    start_time: time = Field(description="Template start time")
    end_time: time = Field(description="Template end time")
    duration_hours: float = Field(description="Duration in hours")

    days_of_week: List[int] = Field(description="Active days of week")
    specialization: SpecializationType = Field(description="Required specialization")
    max_executors: int = Field(description="Maximum executors")

    is_active: bool = Field(description="Template is active")
    auto_assign: bool = Field(description="Auto-assignment enabled")
    recurrence_pattern: Optional[Dict[str, Any]] = Field(description="Recurrence rules")

    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")
    created_by: UUID = Field(description="Creator user ID")

    model_config = ConfigDict(from_attributes=True)


class ShiftAssignmentRequest(BaseModel):
    """Schema for shift assignment request"""
    executor_id: UUID = Field(..., description="Executor user ID")
    assignment_method: str = Field(default="manual", description="Assignment method (manual, ai, auto)")
    notes: Optional[str] = Field(default=None, description="Assignment notes")

    model_config = ConfigDict(from_attributes=True)


class ShiftAssignmentCreate(BaseModel):
    """Schema for creating a shift assignment"""
    shift_id: UUID = Field(..., description="Shift ID")
    executor_id: UUID = Field(..., description="Executor user ID")
    assignment_method: str = Field(..., description="Assignment method (manual, ai, auto)")
    confidence_score: Optional[float] = Field(default=None, ge=0, le=1, description="AI confidence")

    model_config = ConfigDict(from_attributes=True)


class ShiftAssignmentResponse(BaseModel):
    """Schema for shift assignment response"""
    id: UUID = Field(description="Assignment ID")
    shift_id: UUID = Field(description="Shift ID")
    executor_id: UUID = Field(description="Executor user ID")

    assigned_at: datetime = Field(description="Assignment timestamp")
    assigned_by: UUID = Field(description="Assigner user ID")

    assignment_method: str = Field(description="Assignment method")
    confidence_score: Optional[float] = Field(description="AI confidence score")
    notes: Optional[str] = Field(default=None, description="Assignment notes")

    is_active: bool = Field(description="Assignment is active")

    # Performance tracking
    acceptance_time: Optional[datetime] = Field(description="Acceptance timestamp")
    start_time: Optional[datetime] = Field(description="Work start timestamp")
    completion_time: Optional[datetime] = Field(description="Completion timestamp")

    model_config = ConfigDict(from_attributes=True)


class ShiftBulkCreate(BaseModel):
    """Schema for bulk shift creation"""
    shifts: List[ShiftCreate] = Field(..., max_length=50, description="List of shifts to create")
    template_id: Optional[UUID] = Field(default=None, description="Template for all shifts")

    model_config = ConfigDict(from_attributes=True)


class ShiftBulkResponse(BaseModel):
    """Schema for bulk operation response"""
    created_count: int = Field(description="Number of shifts created")
    failed_count: int = Field(description="Number of failed creations")
    created_shifts: List[UUID] = Field(description="IDs of created shifts")
    errors: List[Dict[str, Any]] = Field(description="Creation errors")

    model_config = ConfigDict(from_attributes=True)