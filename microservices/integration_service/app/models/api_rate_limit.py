"""
API Rate Limit Model
UK Management Bot - Integration Service

Tracks API rate limit usage for external services.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy import String, Integer, DateTime, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class APIRateLimit(Base):
    """
    API Rate Limit Tracking

    Tracks API usage against rate limits for external services.
    Prevents exceeding quotas and enables cost monitoring.
    """
    __tablename__ = "api_rate_limits"

    # Primary Key
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Multi-tenancy
    management_company_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Tenant isolation - Management Company ID"
    )

    # Service Reference
    service_id: Mapped[UUID] = mapped_column(
        nullable=False,
        index=True,
        comment="Reference to external_services.id"
    )

    service_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Service name for quick lookup"
    )

    # Rate Limit Window
    window_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Window type: minute, hour, day, month"
    )

    window_start: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
        comment="Start of rate limit window"
    )

    window_end: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
        comment="End of rate limit window"
    )

    # Usage Tracking
    request_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of requests in this window"
    )

    success_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Successful requests"
    )

    error_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Failed requests"
    )

    rate_limited_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Requests blocked due to rate limiting"
    )

    # Limits
    max_requests: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Maximum requests allowed in window"
    )

    remaining_requests: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Remaining requests in window"
    )

    # Performance Metrics
    total_duration_ms: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Total request duration in milliseconds"
    )

    avg_duration_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Average request duration"
    )

    min_duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Minimum request duration"
    )

    max_duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Maximum request duration"
    )

    # Data Transfer
    total_bytes_sent: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Total bytes sent in requests"
    )

    total_bytes_received: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Total bytes received in responses"
    )

    # Cost Tracking
    total_cost: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Total API cost for this window"
    )

    cost_currency: Mapped[Optional[str]] = mapped_column(
        String(3),
        nullable=True,
        comment="Currency code: USD, EUR, etc."
    )

    # Status
    is_rate_limited: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Currently rate limited"
    )

    rate_limit_reset_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="When rate limit will reset"
    )

    # Operation Breakdown
    operation_counts: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Request counts by operation type"
    )

    # Audit Fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<APIRateLimit(id={self.id}, "
            f"service={self.service_name}, "
            f"window={self.window_type}, "
            f"usage={self.request_count}/{self.max_requests})>"
        )

    @property
    def utilization_percent(self) -> float:
        """Calculate rate limit utilization percentage"""
        if self.max_requests == 0:
            return 0.0
        return (self.request_count / self.max_requests) * 100

    @property
    def is_near_limit(self) -> bool:
        """Check if approaching rate limit (>80% utilized)"""
        return self.utilization_percent >= 80.0
