"""Автомобили и их привязка к квартирам. §5.3, §12.

``vehicles`` — постоянный автомобиль с нормализованным номером (§12). ``UNIQUE
plate_number_normalized WHERE status<>'archived'`` (решение CTO #6): один активный
носитель номера, архив исключён. ``vehicle_apartments`` — связь авто↔квартира с
типом отношения и статусом модерации; лимит постоянных авто считается по числу
активных связей квартиры (§5.3).
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
    Text,
    text,
)

from uk_management_bot.database.session import Base
from .base import created_at_column, pk_column, updated_at_column
from .enums import (
    VehicleApartmentRelationType,
    VehicleApartmentStatus,
    VehicleStatus,
    in_clause,
)


class Vehicle(Base):
    """Постоянный автомобиль (§5.3, нормализация §12)."""

    __tablename__ = "vehicles"

    id = pk_column()
    # Нормализация номера (§12): original/normalized/country/type + recognition_key.
    plate_number_original = Column(String(32), nullable=False)
    plate_number_normalized = Column(String(32), nullable=False)
    plate_country = Column(String(8), nullable=True)
    plate_type = Column(String(32), nullable=True)
    # Ключ поиска кандидатов по омоглифам/fuzzy (§12) — без молчаливого слияния.
    recognition_key = Column(String(32), nullable=True, index=True)
    make = Column(String(64), nullable=True)
    model = Column(String(64), nullable=True)
    color = Column(String(32), nullable=True)
    vehicle_class = Column(String(32), nullable=True)
    status = Column(
        String(16), nullable=False, server_default=VehicleStatus.ACTIVE.value
    )
    blocked_reason = Column(Text, nullable=True)
    blocked_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    blocked_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = created_at_column()
    updated_at = updated_at_column()

    __table_args__ = (
        CheckConstraint(in_clause("status", VehicleStatus), name="ck_vehicles_status"),
        # Решение CTO #6: уникальность нормализованного номера среди неархивных.
        Index(
            "uq_vehicles_plate_normalized_active",
            "plate_number_normalized",
            unique=True,
            postgresql_where=text("status <> 'archived'"),
            sqlite_where=text("status <> 'archived'"),
        ),
    )


class VehicleApartment(Base):
    """Связь автомобиль↔квартира с типом отношения и модерацией. §5.3."""

    __tablename__ = "vehicle_apartments"

    id = pk_column()
    vehicle_id = Column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    apartment_id = Column(
        Integer,
        ForeignKey("apartments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relation_type = Column(String(16), nullable=False)
    status = Column(
        String(16),
        nullable=False,
        server_default=VehicleApartmentStatus.PENDING.value,
    )
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    approved_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = created_at_column()
    updated_at = updated_at_column()

    __table_args__ = (
        CheckConstraint(
            in_clause("relation_type", VehicleApartmentRelationType),
            name="ck_vehicle_apartments_relation_type",
        ),
        CheckConstraint(
            in_clause("status", VehicleApartmentStatus),
            name="ck_vehicle_apartments_status",
        ),
    )
