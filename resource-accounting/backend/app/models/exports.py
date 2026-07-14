import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import Timestamped, UUIDPk

EXPORT_STATUSES = ("draft", "generated", "sent", "cancelled")
EXPORT_FORMATS = ("xlsx", "csv", "pdf")


class Export(Base, UUIDPk, Timestamped):
    """Reconciliation act header: immutable snapshot after generation."""

    __tablename__ = "exports"
    __table_args__ = (Index("ix_exports_lookup", "tenant_id", "reporting_period_id", "provider_id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    reporting_period_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reporting_periods.id"), nullable=False)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("providers.id"))
    format: Mapped[str] = mapped_column(String(10), nullable=False, default="xlsx")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="generated")
    is_correction: Mapped[bool] = mapped_column(default=False, nullable=False)
    filters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    file_name: Mapped[str] = mapped_column(String(300), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 of row snapshot
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    sent_channel: Mapped[str | None] = mapped_column(String(100))
    sent_comment: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    period = relationship("ReportingPeriod", lazy="joined")
    provider = relationship("Provider", lazy="joined")
    rows: Mapped[list["ExportRow"]] = relationship(
        back_populates="export", lazy="selectin", order_by="ExportRow.row_index"
    )


class ExportRow(Base, UUIDPk):
    """Append-only snapshot of one meter line inside a generated act."""

    __tablename__ = "export_rows"

    export_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exports.id"), nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)

    export = relationship("Export", back_populates="rows")
