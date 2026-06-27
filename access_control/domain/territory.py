"""Территория: парковочные зоны и их связь с фазами ЖК (yards). §5.1.

``parking_zones`` — парковочная зона с режимом offline (§8.1) и лимитом
постоянных авто на квартиру. ``parking_zone_yards`` — M:N связь зоны с
существующими ``yards`` (фазами ЖК): одна зона может обслуживать несколько фаз.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from uk_management_bot.database.session import Base
from .base import (
    JSONB_PORTABLE,
    created_at_column,
    pk_column,
    updated_at_column,
)
from .enums import OfflineMode, ParkingType, in_clause


class ParkingZone(Base):
    """Парковочная зона пилота (§5.1)."""

    __tablename__ = "parking_zones"

    id = pk_column()
    code = Column(String(64), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # Режим offline точки въезда (§8.1); пилот по умолчанию fail_closed.
    offline_mode = Column(
        String(32), nullable=False, server_default=OfflineMode.FAIL_CLOSED.value
    )
    # Тип парковки (§5.1): assigned — закреплённые за квартирой места;
    # shared — общая зона (все авто обслуживаемых квартир). По умолчанию shared.
    parking_type = Column(
        String(16), nullable=False, server_default=ParkingType.SHARED.value
    )
    # Информативная ёмкость общей зоны (§10.3); NULL — не задана. Переполнение
    # сейчас НЕ блокируется (учёт заездов), enforce — после оснащения выезда.
    capacity = Column(Integer, nullable=True)
    # Лимит активных постоянных авто на квартиру (§5.3); NULL — без лимита.
    # Для shared-зоны используется как ГИБКИЙ кап (превышение → manual_review).
    max_permanent_vehicles_per_apartment = Column(Integer, nullable=True)
    extra = Column(JSONB_PORTABLE, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = created_at_column()
    updated_at = updated_at_column()

    __table_args__ = (
        CheckConstraint(
            in_clause("offline_mode", OfflineMode),
            name="ck_parking_zones_offline_mode",
        ),
        CheckConstraint(
            in_clause("parking_type", ParkingType),
            name="ck_parking_zones_parking_type",
        ),
    )


class ParkingZoneYard(Base):
    """Связь парковочной зоны с фазой ЖК (yards). §5.1."""

    __tablename__ = "parking_zone_yards"

    id = pk_column()
    zone_id = Column(
        ForeignKey("parking_zones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # FK на существующие yards — INTEGER (их фактический PK).
    yard_id = Column(
        Integer,
        ForeignKey("yards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = created_at_column()

    __table_args__ = (
        UniqueConstraint("zone_id", "yard_id", name="uq_parking_zone_yards_zone_yard"),
    )
