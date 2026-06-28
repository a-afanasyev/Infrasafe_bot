"""Канонические строковые enum'ы домена access_control (Ф2).

Паттерн ``UserApartmentStatus``: ``str``-подкласс → wire-совместим со строковой
колонкой (член равен своему значению, SQLAlchemy биндит value). Значения —
канонические строки из DATA_MODEL_PILOT «Enum». Колонки используют их в
``CheckConstraint`` (см. модели), без нативных PG ENUM-типов.
"""
from __future__ import annotations

import enum


class VehicleStatus(str, enum.Enum):
    """vehicles.status."""

    ACTIVE = "active"
    BLOCKED = "blocked"
    ARCHIVED = "archived"


class VehicleApartmentRelationType(str, enum.Enum):
    """vehicle_apartments.relation_type."""

    OWNER = "owner"
    TENANT = "tenant"
    FAMILY = "family"
    SERVICE = "service"


class VehicleApartmentStatus(str, enum.Enum):
    """vehicle_apartments.status."""

    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class ParkingType(str, enum.Enum):
    """parking_zones.parking_type (§5.1): закреплённые места / общая зона."""

    ASSIGNED = "assigned"
    SHARED = "shared"


class SpotStatus(str, enum.Enum):
    """parking_spots.status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class OwnershipType(str, enum.Enum):
    """parking_spot_assignments.ownership_type (закрепление за квартирой)."""

    OWNED = "owned"
    RENTED = "rented"


class EntryConfirmationResponse(str, enum.Enum):
    """access_entry_confirmations.response — ответ жителя на спорный въезд (§9.4).

    Совещательный сигнал: ``confirm`` — это мой/санкционированный въезд,
    ``deny`` — въезд не мой/не санкционирован. Решение оператора (§9.5) от
    этого ответа не зависит автоматически.
    """

    CONFIRM = "confirm"
    DENY = "deny"


class SpotAssignmentStatus(str, enum.Enum):
    """parking_spot_assignments.status."""

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    ARCHIVED = "archived"


class PresenceStatus(str, enum.Enum):
    """vehicle_presence_sessions.status (§10.3): открытая/закрытая сессия присутствия.

    Въезд открывает сессию (``open``), выезд/ручное освобождение закрывает
    (``closed``). «Занятость» места = число открытых сессий квартиры в зоне.
    """

    OPEN = "open"
    CLOSED = "closed"


class PassType(str, enum.Enum):
    """access_passes.pass_type (логика пилота — только ``taxi``)."""

    GUEST = "guest"
    TAXI = "taxi"
    DELIVERY = "delivery"
    COURIER = "courier"
    SERVICE = "service"
    CONTRACTOR = "contractor"
    EMERGENCY = "emergency"


class PassStatus(str, enum.Enum):
    """access_passes.status."""

    ACTIVE = "active"
    USED = "used"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ResidentRequestStatus(str, enum.Enum):
    """resident_access_requests.status."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class DecisionType(str, enum.Enum):
    """access_decisions.decision."""

    ALLOW = "allow"
    DENY = "deny"
    MANUAL_REVIEW = "manual_review"


class DecisionStatus(str, enum.Enum):
    """access_decisions.status (lifecycle §9.5, append-only переходы)."""

    PENDING_REVIEW = "pending_review"
    ALLOWED = "allowed"
    ALLOWED_MANUALLY = "allowed_manually"
    DENIED = "denied"
    DENIED_MANUALLY = "denied_manually"
    EXPIRED = "expired"


class DecisionReason(str, enum.Enum):
    """access_decisions.reason (anti_passback в пилоте не генерируется)."""

    PERMANENT_VEHICLE_ALLOWED = "permanent_vehicle_allowed"
    TEMPORARY_PASS_ALLOWED = "temporary_pass_allowed"
    # Зоно-типная логика парковки (§5.1, §7): assigned / shared.
    ASSIGNED_SPOT_ALLOWED = "assigned_spot_allowed"
    SPOT_NOT_ASSIGNED = "spot_not_assigned"
    SPOT_RENTAL_EXPIRED = "spot_rental_expired"
    SHARED_ACCESS_ALLOWED = "shared_access_allowed"
    PER_APARTMENT_LIMIT_EXCEEDED = "per_apartment_limit_exceeded"
    # Лимит мест assigned-зоны (§10.3): все купленные/арендованные места квартиры
    # заняты открытыми presence-сессиями → лишний авто на ручной разбор охраны.
    PARKING_SPOT_OCCUPIED = "parking_spot_occupied"
    VEHICLE_NOT_FOUND = "vehicle_not_found"
    VEHICLE_BLOCKED = "vehicle_blocked"
    ZONE_NOT_ALLOWED = "zone_not_allowed"
    PASS_EXPIRED = "pass_expired"
    PASS_ALREADY_USED = "pass_already_used"
    LOW_CONFIDENCE = "low_confidence"
    POSSIBLE_PLATE_CLONE = "possible_plate_clone"
    ANTI_PASSBACK_VIOLATION = "anti_passback_violation"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class OfflineMode(str, enum.Enum):
    """offline_mode (пилот — только fail_closed, §8.1)."""

    FAIL_CLOSED = "fail_closed"
    CACHED_PERMANENT_ONLY = "cached_permanent_only"


class EdgeControllerStatus(str, enum.Enum):
    """edge_controllers.status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DECOMMISSIONED = "decommissioned"


class CommandStatus(str, enum.Enum):
    """barrier_commands.status."""

    PENDING = "pending"
    LEASED = "leased"
    ACKED = "acked"
    DEAD = "dead"


class CommandType(str, enum.Enum):
    """barrier_commands.command_type."""

    OPEN_BARRIER = "open_barrier"


class Direction(str, enum.Enum):
    """direction (пилот фиксирует только entry, §10.3)."""

    ENTRY = "entry"
    EXIT = "exit"


class EventSource(str, enum.Enum):
    """source: connected | edge_offline (§8.4)."""

    CONNECTED = "connected"
    EDGE_OFFLINE = "edge_offline"


def values(enum_cls: type[enum.Enum]) -> tuple[str, ...]:
    """Кортеж значений enum — для построения ``CheckConstraint`` IN (...)."""
    return tuple(member.value for member in enum_cls)


def in_clause(column: str, enum_cls: type[enum.Enum]) -> str:
    """SQL-фрагмент ``column IN ('a','b',...)`` для CheckConstraint."""
    quoted = ", ".join(f"'{v}'" for v in values(enum_cls))
    return f"{column} IN ({quoted})"
