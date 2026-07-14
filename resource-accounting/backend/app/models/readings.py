import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import Timestamped, UUIDPk

PERIOD_STATUSES = ("open", "review", "submitted", "closed")
READING_STATUSES = ("ok", "warning", "error", "missing")
READING_KINDS = ("normal", "rollover", "replacement", "correction")
MISSING_REASONS = ("no_access", "broken", "replaced", "other")


class ReportingPeriod(Base, UUIDPk, Timestamped):
    __tablename__ = "reporting_periods"
    __table_args__ = (UniqueConstraint("tenant_id", "month", name="uq_periods_tenant_month"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    month: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM, Asia/Tashkent
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")


class Reading(Base, UUIDPk, Timestamped):
    """Current accepted reading of a meter for a period (one live row per meter+period)."""

    __tablename__ = "readings"
    __table_args__ = (
        UniqueConstraint("meter_id", "reporting_period_id", name="uq_readings_meter_period"),
        Index("ix_readings_period_status", "reporting_period_id", "status"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    meter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meters.id"), nullable=False)
    reporting_period_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reporting_periods.id"), nullable=False)

    value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))  # None => missing
    read_at: Mapped[date | None] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    previous_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    consumption: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="missing")
    validation_message: Mapped[str | None] = mapped_column(Text)
    missing_reason: Mapped[str | None] = mapped_column(String(30))
    comment: Mapped[str | None] = mapped_column(Text)
    photo_file_id: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    meter = relationship("Meter", lazy="joined")
    period = relationship("ReportingPeriod", lazy="joined")
    revisions: Mapped[list["ReadingRevision"]] = relationship(
        back_populates="reading", lazy="selectin", order_by="ReadingRevision.created_at"
    )


class ReadingRevision(Base, UUIDPk):
    """Append-only history of every change/correction to a reading."""

    __tablename__ = "reading_revisions"

    reading_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("readings.id"), nullable=False)
    old_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    new_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    reason: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    reading = relationship("Reading", back_populates="revisions")


class AnomalyRule(Base, UUIDPk, Timestamped):
    """Configurable anomaly thresholds per tenant + resource type (ТЗ §5.4)."""

    __tablename__ = "anomaly_rules"
    __table_args__ = (UniqueConstraint("tenant_id", "resource_type", name="uq_anomaly_rules"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)
    abs_threshold: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    pct_change_threshold: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))  # % vs previous month
    avg_window_months: Mapped[int] = mapped_column(default=6, nullable=False)
    avg_deviation_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))  # % vs rolling average
