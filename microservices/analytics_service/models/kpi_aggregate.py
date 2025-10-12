"""
KPI Aggregate Model - Time-series Aggregated Data

Sprint 16-18: Analytics Service
Week 6, Task 6.1: Time-series Aggregations
Author: Analytics Team
Date: October 6, 2025

Stores pre-calculated KPI values at different time granularities:
- Daily aggregates
- Weekly aggregates
- Monthly aggregates
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Index, UniqueConstraint, DECIMAL
from sqlalchemy.dialects.postgresql import JSONB

from db.session import Base


class KPIAggregate(Base):
    """
    Stores pre-calculated KPI values for efficient historical queries.

    Time granularities:
    - daily: Aggregated by day
    - weekly: Aggregated by week (ISO week)
    - monthly: Aggregated by month

    This allows fast queries for dashboards and reports without
    recalculating from raw events every time.
    """

    __tablename__ = "kpi_aggregates"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # KPI identification
    kpi_name = Column(String(100), nullable=False, index=True)
    """KPI name: active_shifts, shift_completion_rate, etc."""

    # Time dimensions
    granularity = Column(String(20), nullable=False, index=True)
    """Time granularity: daily, weekly, monthly"""

    period_start = Column(DateTime, nullable=False, index=True)
    """Start of the time period (UTC)"""

    period_end = Column(DateTime, nullable=False)
    """End of the time period (UTC)"""

    period_date = Column(Date, nullable=False, index=True)
    """Date for easy filtering (YYYY-MM-DD)"""

    # KPI values
    value = Column(DECIMAL(10, 2), nullable=False)
    """Main KPI value (e.g., 42.5)"""

    unit = Column(String(50), nullable=True)
    """Unit of measurement: count, percent, hours, minutes"""

    kpi_type = Column(String(50), nullable=True)
    """KPI type: gauge, counter, histogram"""

    # Additional data
    extra_data = Column(JSONB, nullable=True)
    """
    Additional metadata:
    - breakdown: {created: 100, completed: 80, cancelled: 5}
    - source_event_count: 185
    - calculation_method: "sum", "avg", "rate"
    - data_quality: "complete", "partial", "estimated"
    """

    # Audit fields
    calculated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    """When this aggregate was calculated"""

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes for efficient queries
    __table_args__ = (
        # Unique constraint: one aggregate per KPI + granularity + period
        UniqueConstraint(
            "kpi_name",
            "granularity",
            "period_date",
            name="uq_kpi_granularity_period"
        ),
        # Composite indexes for common queries
        Index(
            "idx_kpi_granularity_date",
            "kpi_name",
            "granularity",
            "period_date"
        ),
        Index(
            "idx_granularity_date",
            "granularity",
            "period_date"
        ),
    )

    def __repr__(self):
        return (
            f"<KPIAggregate("
            f"kpi={self.kpi_name}, "
            f"granularity={self.granularity}, "
            f"period={self.period_date}, "
            f"value={self.value}"
            f")>"
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "kpi_name": self.kpi_name,
            "granularity": self.granularity,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "period_date": self.period_date.isoformat() if self.period_date else None,
            "value": float(self.value) if self.value else 0.0,
            "unit": self.unit,
            "kpi_type": self.kpi_type,
            "extra_data": self.extra_data,
            "calculated_at": self.calculated_at.isoformat() if self.calculated_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
