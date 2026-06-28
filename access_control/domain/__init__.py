"""Доменный слой access_control: 18 пилотных сущностей (§5.2).

Импорт этого пакета регистрирует все пилотные модели на общем ``Base``
(``uk_management_bot.database.session.Base``) — том же declarative Base, что
использует alembic ``env.py`` и тестовый ``create_all``. Поэтому достаточно
``import access_control.domain``, чтобы таблицы попали в ``Base.metadata``.

``vehicle_presence_sessions`` сюда НЕ входит — вне пилота (§10.3, §14.2).

Группировка по файлам: territory, equipment, vehicles, passes, events,
commands, audit. Enum'ы — в ``enums``.
"""
from __future__ import annotations

from .audit import AccessAuditLog, ManualOpening
from .commands import BarrierCommand
from .equipment import AccessBarrier, AccessCamera, AccessGate, EdgeController
from .events import (
    AccessDecision,
    AccessEntryConfirmation,
    AccessEvent,
    CameraEvent,
    ControllerSyncEvent,
)
from .parking import ParkingSpot, ParkingSpotAssignment
from .passes import AccessPass, AccessRule, ResidentAccessRequest
from .territory import ParkingZone, ParkingZoneYard
from .vehicles import Vehicle, VehicleApartment

__all__ = [
    # territory
    "ParkingZone",
    "ParkingZoneYard",
    # parking (assigned/shared)
    "ParkingSpot",
    "ParkingSpotAssignment",
    # equipment
    "EdgeController",
    "AccessGate",
    "AccessCamera",
    "AccessBarrier",
    # vehicles
    "Vehicle",
    "VehicleApartment",
    # passes
    "AccessRule",
    "AccessPass",
    "ResidentAccessRequest",
    # events
    "CameraEvent",
    "AccessDecision",
    "AccessEvent",
    "AccessEntryConfirmation",
    "ControllerSyncEvent",
    # commands
    "BarrierCommand",
    # audit
    "ManualOpening",
    "AccessAuditLog",
]
