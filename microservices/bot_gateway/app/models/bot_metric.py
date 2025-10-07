"""
Bot Metrics Model
UK Management Bot - Bot Gateway Service

Tracks bot usage metrics and analytics.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from sqlalchemy import String, BigInteger, DateTime, Float, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import BaseModel


class BotMetric(BaseModel):
    """
    Bot Usage Metrics

    Tracks various bot metrics for analytics and monitoring:
    - Command usage
    - Message processing times
    - Error rates
    - User engagement
    """

    __tablename__ = "bot_metrics"

    # Metric identification
    metric_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Metric type: command_usage, response_time, error, user_action, etc."
    )

    metric_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Specific metric name"
    )

    # Metric value
    value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Metric value (count, duration ms, etc.)"
    )

    unit: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Unit of measurement: count, ms, bytes, etc."
    )

    # User context
    user_id: Mapped[Optional[UUID]] = mapped_column(
        nullable=True,
        index=True,
        comment="Reference to User Service user_id"
    )

    telegram_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="Telegram user ID"
    )

    # Temporal context
    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
        comment="Metric timestamp"
    )

    date: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
        comment="Date for daily aggregation"
    )

    hour: Mapped[int] = mapped_column(
        nullable=False,
        index=True,
        comment="Hour (0-23) for hourly aggregation"
    )

    # Context metadata
    command: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="Related command if applicable"
    )

    handler_service: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="Handler service that processed the request"
    )

    status: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment="Status: success, error, timeout, etc."
    )

    # Error tracking
    error_code: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="Error code if metric tracks an error"
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Error message if applicable"
    )

    # Additional data
    tags: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Tags for filtering and grouping"
    )

    metadata: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional metric metadata"
    )

    # Indexes for performance
    __table_args__ = (
        Index("ix_bot_metrics_type_date", "metric_type", "date"),
        Index("ix_bot_metrics_name_timestamp", "metric_name", "timestamp"),
        Index("ix_bot_metrics_user_date", "user_id", "date"),
        Index("ix_bot_metrics_command_date", "command", "date"),
        Index("ix_bot_metrics_status_date", "status", "date"),
        Index("ix_bot_metrics_date_hour", "date", "hour"),
    )

    def __repr__(self) -> str:
        return (
            f"<BotMetric(type={self.metric_type}, "
            f"name={self.metric_name}, "
            f"value={self.value})>"
        )

    @classmethod
    def create_command_usage(
        cls,
        command: str,
        user_id: Optional[UUID] = None,
        telegram_id: Optional[int] = None,
        success: bool = True,
        **kwargs
    ) -> "BotMetric":
        """Create command usage metric"""
        now = datetime.utcnow()
        return cls(
            metric_type="command_usage",
            metric_name=command,
            value=1.0,
            unit="count",
            user_id=user_id,
            telegram_id=telegram_id,
            command=command,
            status="success" if success else "error",
            timestamp=now,
            date=now.date(),
            hour=now.hour,
            **kwargs
        )

    @classmethod
    def create_response_time(
        cls,
        handler_service: str,
        duration_ms: float,
        command: Optional[str] = None,
        **kwargs
    ) -> "BotMetric":
        """Create response time metric"""
        now = datetime.utcnow()
        return cls(
            metric_type="response_time",
            metric_name=f"{handler_service}_response",
            value=duration_ms,
            unit="ms",
            handler_service=handler_service,
            command=command,
            status="success",
            timestamp=now,
            date=now.date(),
            hour=now.hour,
            **kwargs
        )
