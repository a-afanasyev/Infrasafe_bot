"""Учёт заездов по парковочной зоне (§10.3, §14.2).

В пилоте детектируется ТОЛЬКО въезд (presence/выезд off, §10.3): переполнение НЕ
блокируется, считается лишь число РАЗРЕШЁННЫХ въездов. Структурно заложено
вычитание выездов — когда оснастят выездные камеры (``direction='exit'``),
``occupancy = entries - exits`` начнёт отражать реальную занятость без изменения
вызывающего кода. Сейчас ``exits`` всегда 0, ``occupancy == entries``.

Источник — иммутабельный журнал ``access_events`` (allow-проезды по зоне), не
сырые camera_events: занятость считается по фактически разрешённым проездам.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ZoneOccupancy:
    """Снимок учёта заездов зоны. ``occupancy = entries - exits`` (§10.3)."""

    zone_id: int
    entries: int
    exits: int
    occupancy: int


def _count_allowed(db: Session, zone_id: int, direction: str) -> int:
    return int(
        db.execute(
            text(
                "SELECT count(*) FROM access_events "
                "WHERE zone_id = :z AND direction = :d AND decision = 'allow'"
            ),
            {"z": zone_id, "d": direction},
        ).scalar_one()
    )


def zone_occupancy(db: Session, zone_id: int) -> ZoneOccupancy:
    """Учёт заездов зоны: число разрешённых въездов (минус выездов — задел).

    Пилот фиксирует только entry (§10.3) → ``exits`` обычно 0. Когда выездные
    камеры включат и пойдут allow/``exit`` события, ``occupancy`` станет реальной
    занятостью без правок API.
    """
    entries = _count_allowed(db, zone_id, "entry")
    exits = _count_allowed(db, zone_id, "exit")
    return ZoneOccupancy(
        zone_id=zone_id,
        entries=entries,
        exits=exits,
        occupancy=entries - exits,
    )
