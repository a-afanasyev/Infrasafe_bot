"""Парковочные места и их закрепление за квартирами. §5.1, §7.

``parking_spots`` — физическое/логическое место в зоне (assigned-зона).
``parking_spot_assignments`` — закрепление места ЗА КВАРТИРОЙ (решение владельца):
любой активный авто квартиры (через ``vehicle_apartments``) пользуется её местом.
Срок аренды задаётся ``valid_from/until``; просроченное закрепление → Decision
Engine отдаёт ``spot_rental_expired`` (§7).
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)

from uk_management_bot.database.session import Base
from .base import created_at_column, pk_column, updated_at_column
from .enums import (
    OwnershipType,
    PresenceStatus,
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
    # Тумблер лимита мест (§10.3): TRUE — авто квартиры сверх числа её активных мест
    # не пускается (manual_review parking_spot_occupied); FALSE — житель/менеджер
    # временно снял лимит (2-я машина), доступ без проверки занятости.
    enforce_limit = Column(
        Boolean, nullable=False, server_default=text("true")
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


class VehiclePresenceSession(Base):
    """Сессия присутствия авто в зоне (§10.3): въезд открывает, выезд закрывает.

    «Занятость» места assigned-зоны = число ОТКРЫТЫХ сессий квартиры в зоне.
    Мутабельна (open→closed через UPDATE) — НЕ append-only (без hash-chain/триггера).
    Частичный ``UNIQUE(vehicle_id, zone_id) WHERE status='open'`` гарантирует ровно
    одну открытую сессию авто в зоне (повторный въезд при открытой → manual_review).
    """

    __tablename__ = "vehicle_presence_sessions"

    id = pk_column()
    vehicle_id = Column(
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    apartment_id = Column(
        Integer,
        ForeignKey("apartments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    zone_id = Column(
        ForeignKey("parking_zones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entered_at = Column(DateTime(timezone=True), nullable=False)
    exited_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(
        String(8), nullable=False, server_default=PresenceStatus.OPEN.value
    )
    entry_camera_event_id = Column(
        ForeignKey("camera_events.id", ondelete="SET NULL"), nullable=True
    )
    exit_camera_event_id = Column(
        ForeignKey("camera_events.id", ondelete="SET NULL"), nullable=True
    )
    closed_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    close_reason = Column(String(32), nullable=True)
    created_at = created_at_column()

    __table_args__ = (
        CheckConstraint(
            in_clause("status", PresenceStatus),
            name="ck_vehicle_presence_sessions_status",
        ),
        Index(
            "ix_vehicle_presence_sessions_zone_status",
            "zone_id",
            "status",
        ),
        Index(
            "ix_vehicle_presence_sessions_apartment_zone_status",
            "apartment_id",
            "zone_id",
            "status",
        ),
        # Ровно одна открытая сессия авто в зоне (§10.3).
        Index(
            "uq_vehicle_presence_open_vehicle_zone",
            "vehicle_id",
            "zone_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
            sqlite_where=text("status = 'open'"),
        ),
    )
