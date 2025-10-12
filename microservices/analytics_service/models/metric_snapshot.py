"""
MetricSnapshot Model - Point-in-time metrics

Task 1.2: Core Data Models
Stores calculated metrics at specific points in time
"""

from datetime import datetime
from typing import Dict, Any, Optional

from sqlalchemy import Column, String, DateTime, Float, Integer, Index
from sqlalchemy.dialects.postgresql import JSONB

from db.session import Base


class MetricSnapshot(Base):
    """
    Point-in-time metric snapshots

    Stores calculated KPI values at specific timestamps
    """

    __tablename__ = "metric_snapshots"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Metric identification
    metric_name = Column(String(100), nullable=False, index=True)
    metric_type = Column(String(50), nullable=False)  # counter, gauge, histogram

    # Metric value
    value = Column(Float, nullable=False)
    unit = Column(String(50), nullable=True)  # requests, percent, seconds, etc.

    # Dimensions (for filtering/grouping)
    dimensions = Column(JSONB, nullable=True)  # {service: "shift", status: "active"}

    # Metadata
    extra_data = Column(JSONB, nullable=True)

    # Timestamp
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Indexes for performance
    __table_args__ = (
        Index("idx_metric_name_timestamp", "metric_name", "timestamp"),
        Index("idx_metric_type_timestamp", "metric_type", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<MetricSnapshot(metric={self.metric_name}, value={self.value}, timestamp={self.timestamp})>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "metric_name": self.metric_name,
            "metric_type": self.metric_type,
            "value": self.value,
            "unit": self.unit,
            "dimensions": self.dimensions,
            "extra_data": self.extra_data,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
