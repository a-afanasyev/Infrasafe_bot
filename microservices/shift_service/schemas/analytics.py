# Analytics Schemas for Shift Service
# UK Management Bot - Shift Service

from datetime import datetime, date
from typing import Optional, Dict, Any, List
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from models.analytics import AggregationPeriod, MetricType


class AnalyticsQuery(BaseModel):
    """Schema for analytics query parameters"""
    start_date: date = Field(..., description="Start date for analytics")
    end_date: date = Field(..., description="End date for analytics")
    aggregation_period: AggregationPeriod = Field(default=AggregationPeriod.DAILY, description="Aggregation period")
    executor_id: Optional[UUID] = Field(default=None, description="Filter by executor")
    specialization: Optional[str] = Field(default=None, description="Filter by specialization")

    model_config = ConfigDict(from_attributes=True)


class AnalyticsResponse(BaseModel):
    """Schema for analytics response"""
    period_start: date = Field(description="Period start")
    period_end: date = Field(description="Period end")
    aggregation_period: AggregationPeriod = Field(description="Aggregation period")

    total_shifts: int = Field(description="Total shifts")
    completed_shifts: int = Field(description="Completed shifts")
    cancelled_shifts: int = Field(description="Cancelled shifts")
    transferred_shifts: int = Field(description="Transferred shifts")

    completion_rate: float = Field(description="Completion rate %")
    transfer_rate: float = Field(description="Transfer rate %")
    efficiency_score: float = Field(description="Average efficiency")
    avg_rating: float = Field(description="Average rating")

    model_config = ConfigDict(from_attributes=True)


class PerformanceMetricResponse(BaseModel):
    """Schema for performance metric response"""
    id: UUID = Field(description="Metric ID")
    shift_id: Optional[UUID] = Field(description="Shift ID")
    executor_id: UUID = Field(description="Executor ID")
    metric_type: MetricType = Field(description="Metric type")
    metric_value: float = Field(description="Metric value")
    measurement_date: date = Field(description="Measurement date")

    model_config = ConfigDict(from_attributes=True)


class ShiftStatistics(BaseModel):
    """Schema for shift statistics"""
    total_shifts: int = Field(description="Total shifts")
    active_shifts: int = Field(description="Currently active shifts")
    planned_shifts: int = Field(description="Planned shifts")
    unassigned_shifts: int = Field(description="Unassigned shifts")
    urgent_shifts: int = Field(description="Urgent shifts (priority 3+)")

    model_config = ConfigDict(from_attributes=True)