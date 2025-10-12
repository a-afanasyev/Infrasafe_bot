# Analytics Models for Shift Service
# UK Management Bot - Shift Service

from datetime import datetime, date
from typing import Optional
from enum import Enum
import uuid

from sqlalchemy import (
    Column, String, DateTime, Boolean, Integer, Text,
    JSON, Float, Date, Index, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.sql import func

from . import Base


class MetricType(str, Enum):
    """Metric type enumeration"""
    EFFICIENCY = "efficiency"
    WORKLOAD = "workload"
    COMPLETION_RATE = "completion_rate"
    ASSIGNMENT_TIME = "assignment_time"
    TRANSFER_RATE = "transfer_rate"
    UTILIZATION = "utilization"
    SATISFACTION = "satisfaction"
    GEOGRAPHIC_COVERAGE = "geographic_coverage"


class AggregationPeriod(str, Enum):
    """Aggregation period enumeration"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class ShiftAnalytics(Base):
    """
    Shift analytics aggregation model
    Stores pre-computed analytics for performance
    """
    __tablename__ = "shift_analytics"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Time period
    period_start = Column(Date, nullable=False, index=True)
    period_end = Column(Date, nullable=False, index=True)
    aggregation_period = Column(ENUM(AggregationPeriod), nullable=False, index=True)

    # Scope filters
    executor_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # Null for global analytics
    specialization = Column(String(50), nullable=True, index=True)  # Null for all specializations
    location_filter = Column(JSON)  # Geographic filter criteria

    # Core metrics
    total_shifts = Column(Integer, default=0)
    completed_shifts = Column(Integer, default=0)
    cancelled_shifts = Column(Integer, default=0)
    transferred_shifts = Column(Integer, default=0)

    # Timing metrics
    avg_completion_time_hours = Column(Float)
    avg_assignment_time_minutes = Column(Float)
    total_work_hours = Column(Float)

    # Performance metrics
    completion_rate = Column(Float)  # Percentage
    transfer_rate = Column(Float)  # Percentage
    efficiency_score = Column(Float)  # Average efficiency
    utilization_rate = Column(Float)  # Percentage

    # Quality metrics
    avg_rating = Column(Float)
    satisfaction_score = Column(Float)

    # Geographic metrics
    coverage_area_km2 = Column(Float)
    avg_travel_distance_km = Column(Float)

    # Advanced analytics
    trend_analysis = Column(JSON)  # Trend indicators
    predictions = Column(JSON)  # Predictive analytics
    anomalies = Column(JSON)  # Detected anomalies

    # Metadata
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    data_freshness = Column(DateTime(timezone=True), nullable=False)  # Latest data included

    # Constraints
    __table_args__ = (
        CheckConstraint('period_start <= period_end', name='valid_period'),
        CheckConstraint('total_shifts >= 0', name='non_negative_shifts'),
        CheckConstraint('completion_rate >= 0 AND completion_rate <= 100', name='valid_completion_rate'),
        CheckConstraint('utilization_rate >= 0 AND utilization_rate <= 100', name='valid_utilization'),
        Index('idx_analytics_period_scope', 'period_start', 'executor_id', 'specialization'),
        Index('idx_analytics_aggregation', 'aggregation_period', 'calculated_at'),
    )

    def __repr__(self):
        return f"<ShiftAnalytics(period={self.period_start}-{self.period_end}, executor={self.executor_id})>"


class PerformanceMetric(Base):
    """
    Individual performance metrics for detailed tracking
    Real-time metrics that feed into analytics aggregations
    """
    __tablename__ = "performance_metrics"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # References
    shift_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # Can be shift-specific or general
    executor_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Metric details
    metric_type = Column(ENUM(MetricType), nullable=False, index=True)
    metric_value = Column(Float, nullable=False)
    metric_unit = Column(String(20))  # hours, percentage, score, etc.

    # Context
    measurement_date = Column(Date, nullable=False, index=True)
    context_data = Column(JSON)  # Additional context for the metric

    # Quality and confidence
    confidence_score = Column(Float)  # How confident we are in this metric
    data_source = Column(String(50))  # Source of the metric (ai, manual, calculated)

    # Benchmarking
    benchmark_value = Column(Float)  # Expected/target value
    variance_from_benchmark = Column(Float)  # Difference from benchmark

    # Metadata
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    recorded_by = Column(String(50))  # System component that recorded the metric

    # Constraints
    __table_args__ = (
        CheckConstraint('confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)',
                       name='valid_confidence'),
        Index('idx_metrics_executor_type_date', 'executor_id', 'metric_type', 'measurement_date'),
        Index('idx_metrics_shift_type', 'shift_id', 'metric_type'),
        Index('idx_metrics_date_type', 'measurement_date', 'metric_type'),
    )

    def __repr__(self):
        return f"<PerformanceMetric(type={self.metric_type}, value={self.metric_value}, executor={self.executor_id})>"