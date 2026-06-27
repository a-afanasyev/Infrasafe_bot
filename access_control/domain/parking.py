"""Парковочные места и их закрепление за квартирами. §5.1, §7.

``parking_spots`` — физическое/логическое место в зоне (assigned-зона).
``parking_spot_assignments`` — закрепление места ЗА КВАРТИРОЙ (решение владельца):
любой активный авто квартиры (через ``vehicle_apartments``) пользуется её местом.
Срок аренды задаётся ``valid_from/until``; просроченное закрепление → Decision
Engine отдаёт ``spot_rental_expired`` (§7).
"""
from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from uk_management_bot.database.session import Base
from .base import created_at_column, pk_column, updated_at_column
from .enums import (
    OwnershipType,
    SpotAssignmentStatus,
    SpotStatus,
    in_clause,
)


class ParkingSpot(Base):
    """Парковочное место в зоне (assigned-зона). §5.1."""

    __tablename__ = "parking_spots"

    id = pk_column()
    zone_id = Column(
        ForeignKey("parking_zones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code = Column(String(64), nullable=False)
    status = Column(
        String(16), nullable=False, server_default=SpotStatus.ACTIVE.value
    )
    created_at = created_at_column()
    updated_at = updated_at_column()

    __table_args__ = (
        UniqueConstraint("zone_id", "code", name="uq_parking_spots_zone_code"),
        CheckConstraint(
            in_clause("status", SpotStatus), name="ck_parking_spots_status"
        ),
    )


class ParkingSpotAssignment(Base):
    """Закрепление места за квартирой с типом владения и сроком. §5.1, §7."""

    __tablename__ = "parking_spot_assignments"

    id = pk_column()
    spot_id = Column(
        ForeignKey("parking_spots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    apartment_id = Column(
        Integer,
        ForeignKey("apartments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ownership_type = Column(String(16), nullable=False)
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    status = Column(
        String(16),
        nullable=False,
        server_default=SpotAssignmentStatus.ACTIVE.value,
    )
    approved_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = created_at_column()
    updated_at = updated_at_column()

    __table_args__ = (
        CheckConstraint(
            in_clause("ownership_type", OwnershipType),
            name="ck_parking_spot_assignments_ownership_type",
        ),
        CheckConstraint(
            in_clause("status", SpotAssignmentStatus),
            name="ck_parking_spot_assignments_status",
        ),
        Index(
            "ix_parking_spot_assignments_apartment_status",
            "apartment_id",
            "status",
        ),
        Index(
            "ix_parking_spot_assignments_spot_status",
            "spot_id",
            "status",
        ),
    )
