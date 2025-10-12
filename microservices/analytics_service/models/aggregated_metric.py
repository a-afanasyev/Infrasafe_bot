"""
AggregatedMetric Model - Hourly aggregations

Task 1.2: Core Data Models
Stores hourly aggregated metrics for better query performance
"""

from datetime import datetime
from typing import Dict, Any

from sqlalchemy import Column, String, DateTime, Float, Integer, Index
from sqlalchemy.dialects.postgresql import JSONB

from db.session import Base


class AggregatedMetric(Base):
    """
    Hourly aggregated metrics

    Pre-aggregated metrics for faster queries
    """

    __tablename__ = "aggregated_metrics"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Metric identification
    metric_name = Column(String(100), nullable=False, index=True)
    aggregation_type = Column(String(20), nullable=False)  # hourly, daily

    # Time bucket
    time_bucket = Column(DateTime, nullable=False, index=True)

    # Aggregated values
    count = Column(Integer, nullable=False, default=0)
    sum = Column(Float, nullable=True)
    avg = Column(Float, nullable=True)
    min = Column(Float, nullable=True)
    max = Column(Float, nullable=True)
    p50 = Column(Float, nullable=True)  # median
    p95 = Column(Float, nullable=True)
    p99 = Column(Float, nullable=True)

    # Dimensions
    dimensions = Column(JSONB, nullable=True)

    # Metadata
    extra_data = Column(JSONB, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Indexes for performance
    __table_args__ = (
        Index("idx_metric_time_bucket", "metric_name", "time_bucket"),
        Index("idx_aggregation_time_bucket", "aggregation_type", "time_bucket"),
        Index("idx_unique_metric_bucket", "metric_name", "aggregation_type", "time_bucket", unique=True),
    )

    def __repr__(self) -> str:
        return f"<AggregatedMetric(metric={self.metric_name}, bucket={self.time_bucket}, avg={self.avg})>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "metric_name": self.metric_name,
            "aggregation_type": self.aggregation_type,
            "time_bucket": self.time_bucket.isoformat() if self.time_bucket else None,
            "count": self.count,
            "sum": self.sum,
            "avg": self.avg,
            "min": self.min,
            "max": self.max,
            "p50": self.p50,
            "p95": self.p95,
            "p99": self.p99,
            "dimensions": self.dimensions,
            "extra_data": self.extra_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
