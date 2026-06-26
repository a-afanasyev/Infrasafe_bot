"""Правила доступа, пропуска и заявки жителей. §5.4, §7.

``access_rules`` — явное право (решение CTO #5): зона + срок (valid_from/until) +
разрешённые направления, которые проверяет Decision Engine §7 шаг 6.
``access_passes`` — единая модель временных пропусков с дискриминатором pass_type
(§5.4; логика пилота — только taxi), max_entries/used_entries (§10.3).
``resident_access_requests`` — заявки жителя на постоянный автомобиль.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)

from uk_management_bot.database.session import Base
from .base import (
    JSONB_PORTABLE,
    created_at_column,
    pk_column,
    updated_at_column,
)
from .enums import (
    PassStatus,
    PassType,
    ResidentRequestStatus,
    VehicleApartmentRelationType,
    in_clause,
)


class AccessRule(Base):
    """Явное право доступа: зона + срок + направления (§7 шаг 6, решение CTO #5)."""

    __tablename__ = "access_rules"

    id = pk_column()
    vehicle_id = Column(
        ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=True, index=True
    )
    apartment_id = Column(
        Integer,
        ForeignKey("apartments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    zone_id = Column(
        ForeignKey("parking_zones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Разрешённые направления (пилот — entry). JSONB-массив строк.
    allowed_directions = Column(JSONB_PORTABLE, nullable=True)
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = created_at_column()
    updated_at = updated_at_column()


class AccessPass(Base):
    """Единый временный пропуск (§5.4; пилот — taxi). max_entries/used_entries §10.3."""

    __tablename__ = "access_passes"

    id = pk_column()
    apartment_id = Column(
        Integer,
        ForeignKey("apartments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    pass_type = Column(String(32), nullable=False)
    zone_id = Column(
        ForeignKey("parking_zones.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    plate_number_original = Column(String(32), nullable=True)
    plate_number_normalized = Column(String(32), nullable=True, index=True)
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    # Число успешно разрешённых въездов; одноразовый taxi-pass — max_entries=1 (§10.3).
    max_entries = Column(Integer, nullable=False, server_default="1")
    used_entries = Column(Integer, nullable=False, server_default="0")
    status = Column(
        String(16), nullable=False, server_default=PassStatus.ACTIVE.value
    )
    # Одноразовый код хранится только хэшем (§9.3).
    one_time_code_hash = Column(String(255), nullable=True)
    source = Column(String(32), nullable=True)
    created_at = created_at_column()
    updated_at = updated_at_column()

    __table_args__ = (
        CheckConstraint(
            in_clause("pass_type", PassType), name="ck_access_passes_pass_type"
        ),
        CheckConstraint(
            in_clause("status", PassStatus), name="ck_access_passes_status"
        ),
    )


class ResidentAccessRequest(Base):
    """Заявка жителя на постоянный автомобиль. §6.4."""

    __tablename__ = "resident_access_requests"

    id = pk_column()
    apartment_id = Column(
        Integer,
        ForeignKey("apartments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vehicle_id = Column(
        ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    plate_number_original = Column(String(32), nullable=True)
    plate_number_normalized = Column(String(32), nullable=True)
    relation_type = Column(String(16), nullable=True)
    status = Column(
        String(16),
        nullable=False,
        server_default=ResidentRequestStatus.PENDING.value,
    )
    reviewed_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_comment = Column(Text, nullable=True)
    created_at = created_at_column()
    updated_at = updated_at_column()

    __table_args__ = (
        CheckConstraint(
            in_clause("status", ResidentRequestStatus),
            name="ck_resident_access_requests_status",
        ),
        CheckConstraint(
            "relation_type IS NULL OR "
            + in_clause("relation_type", VehicleApartmentRelationType),
            name="ck_resident_access_requests_relation_type",
        ),
    )
