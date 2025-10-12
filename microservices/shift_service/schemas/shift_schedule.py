# Shift Schedule Schemas for Shift Service
# UK Management Bot - Shift Service

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, field_validator

from models.shift_schedule import ScheduleStatus


class ShiftScheduleCreate(BaseModel):
    """Schema for creating a new shift schedule"""
    date: date = Field(..., description="Schedule date")

    # Planning
    planned_coverage: Optional[Dict[str, int]] = Field(
        default=None,
        description="Planned hourly coverage: {'09:00': 2, '10:00': 3}"
    )
    planned_specialization_coverage: Optional[Dict[str, int]] = Field(
        default=None,
        description="Planned specialization coverage: {'PLUMBER': 2, 'ELECTRICIAN': 1}"
    )

    # Predictions
    predicted_requests: Optional[int] = Field(default=None, ge=0, description="Predicted request count")
    recommended_shifts: Optional[int] = Field(default=None, ge=0, description="AI-recommended shift count")

    # Additional info
    special_conditions: Optional[List[str]] = Field(
        default=None,
        description="Special day conditions: ['holiday', 'event', 'maintenance']"
    )
    notes: Optional[str] = Field(default=None, max_length=500, description="Schedule notes")

    # Metadata
    auto_generated: bool = Field(default=False, description="AI auto-generated flag")

    @field_validator('date')
    @classmethod
    def validate_date_not_past(cls, v):
        """Ensure date is not too far in the past"""
        from datetime import date, timedelta
        if v < date.today() - timedelta(days=365):
            raise ValueError('date cannot be more than 1 year in the past')
        return v

    model_config = ConfigDict(from_attributes=True)


class ShiftScheduleUpdate(BaseModel):
    """Schema for updating an existing shift schedule"""
    # Coverage can be updated
    planned_coverage: Optional[Dict[str, int]] = Field(default=None)
    actual_coverage: Optional[Dict[str, int]] = Field(default=None)
    planned_specialization_coverage: Optional[Dict[str, int]] = Field(default=None)
    actual_specialization_coverage: Optional[Dict[str, int]] = Field(default=None)

    # Predictions and actuals
    predicted_requests: Optional[int] = Field(default=None, ge=0)
    actual_requests: Optional[int] = Field(default=None, ge=0)
    recommended_shifts: Optional[int] = Field(default=None, ge=0)
    actual_shifts: Optional[int] = Field(default=None, ge=0)

    # Optimization metrics
    optimization_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    coverage_percentage: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    load_balance_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    prediction_accuracy: Optional[float] = Field(default=None, ge=0.0, le=100.0)

    # Additional info
    special_conditions: Optional[List[str]] = Field(default=None)
    manual_adjustments: Optional[Dict[str, Any]] = Field(default=None)
    notes: Optional[str] = Field(default=None, max_length=500)

    # Status
    status: Optional[ScheduleStatus] = Field(default=None)
    version: Optional[int] = Field(default=None, ge=1)

    model_config = ConfigDict(from_attributes=True)


class ShiftScheduleResponse(BaseModel):
    """Schema for shift schedule response"""
    id: UUID = Field(description="Schedule ID")
    date: date = Field(description="Schedule date")

    # Coverage
    planned_coverage: Optional[Dict[str, int]] = Field(description="Planned hourly coverage")
    actual_coverage: Optional[Dict[str, int]] = Field(description="Actual hourly coverage")
    planned_specialization_coverage: Optional[Dict[str, int]] = Field(
        description="Planned specialization coverage"
    )
    actual_specialization_coverage: Optional[Dict[str, int]] = Field(
        description="Actual specialization coverage"
    )

    # Predictions and actuals
    predicted_requests: Optional[int] = Field(description="Predicted request count")
    actual_requests: int = Field(description="Actual request count")
    recommended_shifts: Optional[int] = Field(description="AI-recommended shift count")
    actual_shifts: int = Field(description="Actual created shift count")

    # Optimization metrics
    optimization_score: Optional[float] = Field(description="Schedule optimization score (0.0-100.0)")
    coverage_percentage: Optional[float] = Field(description="Coverage fulfillment percentage (0.0-100.0)")
    load_balance_score: Optional[float] = Field(description="Load balance score (0.0-100.0)")
    prediction_accuracy: Optional[float] = Field(description="Prediction accuracy (0.0-100.0)")

    # Computed properties
    coverage_gap_percentage: Optional[float] = Field(description="Coverage gap percentage (0.0-100.0)")
    is_weekend: bool = Field(description="Is weekend (Saturday/Sunday)")
    weekday: int = Field(description="Day of week (1=Monday, 7=Sunday)")
    is_understaffed: bool = Field(description="Coverage < 80%")
    is_overstaffed: bool = Field(description="Coverage > 120%")

    # Additional info
    special_conditions: Optional[List[str]] = Field(description="Special day conditions")
    manual_adjustments: Optional[Dict[str, Any]] = Field(description="Manager manual adjustments")
    notes: Optional[str] = Field(description="Schedule notes")

    # Metadata
    status: str = Field(description="Schedule status")
    created_by: Optional[UUID] = Field(description="Creator user ID")
    auto_generated: bool = Field(description="AI auto-generated flag")
    version: int = Field(description="Schedule version number")

    # Timestamps
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: Optional[datetime] = Field(description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True)


class ShiftScheduleSummary(BaseModel):
    """Lightweight summary schema for schedule lists"""
    id: UUID = Field(description="Schedule ID")
    date: date = Field(description="Schedule date")
    status: str = Field(description="Schedule status")

    # Key metrics only
    coverage_percentage: Optional[float] = Field(description="Coverage percentage")
    predicted_requests: Optional[int] = Field(description="Predicted requests")
    actual_requests: int = Field(description="Actual requests")
    actual_shifts: int = Field(description="Created shifts")

    # Flags
    is_weekend: bool = Field(description="Is weekend")
    is_understaffed: bool = Field(description="Understaffed flag")
    auto_generated: bool = Field(description="Auto-generated flag")

    model_config = ConfigDict(from_attributes=True)


class CoverageGapReport(BaseModel):
    """Coverage gap analysis report"""
    schedule_id: UUID = Field(description="Schedule ID")
    date: date = Field(description="Schedule date")
    total_gap_hours: int = Field(description="Number of hours with coverage gaps")
    gap_details: Dict[str, int] = Field(
        description="Gap by hour: {'09:00': 2, '14:00': 1}"
    )
    gap_hours: List[int] = Field(description="Hours with gaps: [9, 14]")
    critical_gaps: List[str] = Field(description="Hours with gaps >= 3 executors")
    recommendations: List[str] = Field(description="Suggested actions")

    model_config = ConfigDict(from_attributes=True)


class ScheduleOptimizationResult(BaseModel):
    """Schedule optimization analysis result"""
    schedule_id: UUID = Field(description="Schedule ID")
    date: date = Field(description="Schedule date")

    # Metrics
    current_coverage: float = Field(description="Current coverage percentage")
    optimized_coverage: float = Field(description="Projected coverage after optimization")
    improvement: float = Field(description="Coverage improvement percentage")

    # Recommendations
    shifts_to_add: int = Field(description="Number of shifts to add")
    shifts_to_remove: int = Field(description="Number of shifts to remove")
    shifts_to_modify: int = Field(description="Number of shifts to adjust")

    # Details
    suggestions: List[Dict[str, Any]] = Field(description="Detailed optimization suggestions")
    estimated_cost_impact: Optional[float] = Field(description="Estimated cost change")

    model_config = ConfigDict(from_attributes=True)


class ShiftScheduleListResponse(BaseModel):
    """Paginated shift schedule list response"""
    items: List[ShiftScheduleSummary] = Field(description="List of schedules")
    total: int = Field(description="Total number of schedules")
    page: int = Field(description="Current page number")
    size: int = Field(description="Items per page")
    pages: int = Field(description="Total number of pages")

    model_config = ConfigDict(from_attributes=True)
