import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import Timestamped, UUIDPk

RESOURCE_TYPES = ("electricity", "cold_water")
METER_UNITS = ("kWh", "m3")
METER_STATUSES = ("active", "decommissioned", "archived")
LINK_TYPES = ("primary", "consumer")


def normalize_meter_number(raw: str) -> str:
    return " ".join(raw.strip().split()).upper()


class Meter(Base, UUIDPk, Timestamped):
    __tablename__ = "meters"
    __table_args__ = (
        # Partial unique: only active meters must have a unique normalized number.
        Index(
            "uq_meters_active_number",
            "tenant_id",
            "meter_number_normalized",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_meters_primary_object", "tenant_id", "primary_object_id", "resource_type"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    meter_number: Mapped[str] = mapped_column(String(100), nullable=False)
    meter_number_normalized: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)
    unit: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    install_location: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    # Single primary object: source of truth for aggregation (exactly one, enforced by NOT NULL).
    # Additional consumers live in meter_object_links with link_type='consumer'.
    primary_object_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resource_objects.id"), nullable=False)

    provider_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("providers.id"))
    provider_account: Mapped[str | None] = mapped_column(String(100))
    serial_number: Mapped[str | None] = mapped_column(String(100))
    coefficient: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=Decimal("1"))
    max_digits: Mapped[int | None] = mapped_column(Integer)
    installed_at: Mapped[date | None] = mapped_column(Date)
    removed_at: Mapped[date | None] = mapped_column(Date)
    replaces_meter_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("meters.id"))
    photo_file_id: Mapped[str | None] = mapped_column(String(300))
    note: Mapped[str | None] = mapped_column(Text)

    primary_object = relationship("ResourceObject", foreign_keys=[primary_object_id], lazy="joined")
    provider = relationship("Provider", lazy="joined")
    consumer_links: Mapped[list["MeterObjectLink"]] = relationship(
        back_populates="meter", lazy="selectin", cascade="all, delete-orphan"
    )
    tags = relationship("Tag", secondary="meter_tags", lazy="selectin")


class MeterObjectLink(Base, UUIDPk, Timestamped):
    """Consumer links: extra objects/purposes served by a shared meter.

    Consumption is aggregated only into the meter's primary object; consumer links
    participate in filters/context but never duplicate totals (ТЗ §5.3).
    allocation_percent is reserved for a future allocation phase.
    """

    __tablename__ = "meter_object_links"
    __table_args__ = (
        UniqueConstraint("meter_id", "object_id", "link_type", name="uq_meter_object_links"),
        Index("ix_meter_object_links_object", "object_id", "link_type"),
    )

    meter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meters.id"), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resource_objects.id"), nullable=False)
    link_type: Mapped[str] = mapped_column(String(20), nullable=False, default="consumer")
    description: Mapped[str | None] = mapped_column(Text)
    allocation_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    meter: Mapped[Meter] = relationship(back_populates="consumer_links")
    object = relationship("ResourceObject", lazy="joined")


class MeterTag(Base):
    __tablename__ = "meter_tags"
    __table_args__ = (UniqueConstraint("meter_id", "tag_id", name="uq_meter_tags_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meters.id"), nullable=False)
    tag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tags.id"), nullable=False)
