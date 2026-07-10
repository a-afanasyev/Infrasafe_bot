"""Оборудование точки въезда: контроллеры, точки проезда, камеры, шлагбаумы. §5.2.

``edge_controllers`` — edge-контроллер с device-auth (§9.1, решение CTO #8:
api_key_hash + HMAC + nonce + IP allowlist) и режимом offline (§8). ``access_gates``
— точка проезда (направление), ``access_cameras`` — ANPR-камера, ``access_barriers``
— шлагбаум (реле). Точка проезда привязана к зоне; камеры/шлагбаумы — к точке.
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
)

from uk_management_bot.database.session import Base
from .base import (
    JSONB_PORTABLE,
    created_at_column,
    pk_column,
    updated_at_column,
)
from .enums import Direction, EdgeControllerStatus, OfflineMode, in_clause


class EdgeController(Base):
    """Edge-контроллер въезда (device-auth §9.1, offline §8)."""

    __tablename__ = "edge_controllers"

    id = pk_column()
    # Логический идентификатор контроллера в API-пути (/edge/{controller_id}/...).
    controller_uid = Column(String(128), nullable=False, unique=True)
    name = Column(String(255), nullable=True)
    zone_id = Column(
        ForeignKey("parking_zones.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Device-auth: хэш API-ключа устройства (§9.1, решение CTO #8). Общий ключ запрещён.
    # НЕ проверяется до Ф6 (device-auth HMAC): в пилоте идентичность = controller_uid
    # за VPN; HMAC-подпись тела + nonce + timestamp + IP-allowlist — Ф6.
    api_key_hash = Column(String(255), nullable=False)
    ip_allowlist = Column(JSONB_PORTABLE, nullable=True)
    # Опц. привязка к конкретной точке проезда (§6.1, admin-реестр оборудования).
    # use_alter+имя: edge_controllers↔access_gates — циклическая пара FK; помечаем
    # мягкую сторону (nullable SET NULL) use_alter, чтобы SQLAlchemy/autogenerate
    # разрывали цикл (создавали этот FK через ALTER после обеих таблиц). Имя = как
    # в проде (default), чтобы create_all/baseline не расходились со схемой (PRC-05).
    gate_id = Column(
        ForeignKey(
            "access_gates.id",
            ondelete="SET NULL",
            use_alter=True,
            name="edge_controllers_gate_id_fkey",
        ),
        nullable=True,
        index=True,
    )
    # Ссылка на закреплённый публичный ключ устройства (mTLS post-pilot, §9.1) —
    # в пилоте свободный слот, секрет НЕ хранится в БД.
    pinned_public_key_id = Column(String(128), nullable=True)
    offline_mode = Column(
        String(32), nullable=False, server_default=OfflineMode.FAIL_CLOSED.value
    )
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    # Дрейф часов edge относительно backend (§8, heartbeat clock offset), мс.
    clock_offset_ms = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False, server_default="active")
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = created_at_column()
    updated_at = updated_at_column()

    __table_args__ = (
        CheckConstraint(
            in_clause("offline_mode", OfflineMode),
            name="ck_edge_controllers_offline_mode",
        ),
        CheckConstraint(
            in_clause("status", EdgeControllerStatus),
            name="ck_edge_controllers_status",
        ),
    )


class AccessGate(Base):
    """Точка проезда (направление) парковочной зоны. §5.2."""

    __tablename__ = "access_gates"

    id = pk_column()
    code = Column(String(64), nullable=False, unique=True)
    name = Column(String(255), nullable=True)
    zone_id = Column(
        ForeignKey("parking_zones.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    controller_id = Column(
        ForeignKey("edge_controllers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Направление точки (пилот фиксирует только entry, §10.3).
    direction = Column(String(16), nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = created_at_column()
    updated_at = updated_at_column()

    __table_args__ = (
        CheckConstraint(
            in_clause("direction", Direction), name="ck_access_gates_direction"
        ),
    )


class AccessCamera(Base):
    """ANPR-камера точки проезда. §5.2."""

    __tablename__ = "access_cameras"

    id = pk_column()
    code = Column(String(64), nullable=False, unique=True)
    name = Column(String(255), nullable=True)
    gate_id = Column(
        ForeignKey("access_gates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    controller_id = Column(
        ForeignKey("edge_controllers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    direction = Column(String(16), nullable=False)
    # Паспорт камеры (§6.1, admin-реестр оборудования).
    vendor = Column(String(128), nullable=True)
    model = Column(String(128), nullable=True)
    attributes = Column(JSONB_PORTABLE, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = created_at_column()
    updated_at = updated_at_column()

    __table_args__ = (
        CheckConstraint(
            in_clause("direction", Direction), name="ck_access_cameras_direction"
        ),
    )


class AccessBarrier(Base):
    """Шлагбаум (реле) точки проезда. §5.2."""

    __tablename__ = "access_barriers"

    id = pk_column()
    code = Column(String(64), nullable=False, unique=True)
    name = Column(String(255), nullable=True)
    gate_id = Column(
        ForeignKey("access_gates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    controller_id = Column(
        ForeignKey("edge_controllers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Номер реле-канала контроллера, если несколько шлагбаумов на устройстве.
    relay_channel = Column(Integer, nullable=True)
    # Тип реле и гибкая конфигурация шлагбаума (§6.1, admin-реестр оборудования).
    relay_type = Column(String(64), nullable=True)
    config = Column(JSONB_PORTABLE, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = created_at_column()
    updated_at = updated_at_column()
