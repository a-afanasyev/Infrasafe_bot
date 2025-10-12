"""
Metric Schemas - Pydantic models for metrics

Task 1.2: Core Data Models - Pydantic schemas
"""

from datetime import datetime
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class MetricSnapshotBase(BaseModel):
    """Base metric snapshot schema"""
    metric_name: str = Field(..., description="Metric name")
    metric_type: str = Field(..., description="Metric type (counter, gauge, histogram)")
    value: float = Field(..., description="Metric value")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    dimensions: Optional[Dict[str, Any]] = Field(None, description="Dimensions for filtering")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    timestamp: Optional[datetime] = Field(None, description="Metric timestamp")


class MetricSnapshotCreate(MetricSnapshotBase):
    """Schema for creating metric snapshot"""
    pass


class MetricSnapshotResponse(MetricSnapshotBase):
    """Schema for metric snapshot response"""
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class AggregatedMetricBase(BaseModel):
    """Base aggregated metric schema"""
    metric_name: str
    aggregation_type: str = Field(..., description="hourly or daily")
    time_bucket: datetime = Field(..., description="Time bucket start")
    count: int = 0
    sum: Optional[float] = None
    avg: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    p50: Optional[float] = None
    p95: Optional[float] = None
    p99: Optional[float] = None
    dimensions: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class AggregatedMetricCreate(AggregatedMetricBase):
    """Schema for creating aggregated metric"""
    pass


class AggregatedMetricResponse(AggregatedMetricBase):
    """Schema for aggregated metric response"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
