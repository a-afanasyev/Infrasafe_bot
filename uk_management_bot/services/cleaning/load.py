"""Нагрузка уборщиц: этажи и м² мест общего пользования на каждый день недели.

Считается из версий планов и назначений, действующих на дату; меняется план или
привязка — меняется и отчёт. Этажи — без точек (кабина лифта); м² — по площадям дома
(``areas.py``) вместе с точками. Дом без площадей в м² не входит, а попадает в
``missing_areas``. Перегрузка — по м², если норма м² задана, иначе по этажам; при неполных
площадях (есть ``missing_areas``) перегруз по этажам тоже засчитывается.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.cleaning import (
    CleaningAssignment,
    CleaningBuildingSettings,
    CleaningPlanVersion,
)
from uk_management_bot.services.cleaning.areas import AreasError, m2_per_weekday, parse_areas
from uk_management_bot.services.cleaning.planning import WEEKDAYS, PlanError, PlanItem, parse_items, task_for

logger = logging.getLogger(__name__)


def floors_per_weekday(items: Sequence[PlanItem], *, entrance: int) -> list[int]:
    """Этажей к съёмке в подъезде на каждый день недели (пн…вс)."""
    result = []
    for weekday in WEEKDAYS:
        task = task_for(items, (), entrance=entrance, weekday=weekday)
        result.append(sum(slot.startswith("floor:") for slot in task.slots) if task else 0)
    return result


@dataclass
class CleanerLoad:
    by_weekday: list[int] = field(default_factory=lambda: [0] * 7)
    buildings: dict[int, list[int]] = field(default_factory=dict)
    norm: int = 0
    m2_by_weekday: list[float] = field(default_factory=lambda: [0.0] * 7)
    m2_norm: int = 0
    missing_areas: set[int] = field(default_factory=set)  # дома без площадей

    @property
    def week(self) -> int:
        return sum(self.by_weekday)

    @property
    def peak(self) -> int:
        return max(self.by_weekday)

    @property
    def percent(self) -> int:
        return round(self.peak * 100 / self.norm) if self.norm > 0 else 0

    @property
    def m2_peak(self) -> float:
        return round(max(self.m2_by_weekday), 1)

    @property
    def m2_percent(self) -> int:
        return round(self.m2_peak * 100 / self.m2_norm) if self.m2_norm > 0 else 0

    @property
    def overloaded(self) -> bool:
        by_floors = self.norm > 0 and self.peak > self.norm
        if self.m2_norm > 0:
            # Дома без площадей занижают м² — тогда перегруз по этажам не теряется.
            return self.m2_peak > self.m2_norm or (bool(self.missing_areas) and by_floors)
        return by_floors


@dataclass(frozen=True)
class LoadReport:
    cleaners: dict[int, CleanerLoad]
    unassigned: list[tuple[int, int]]  # (дом, подъезд) с работами по плану, но без ответственного


def _valid_on(model, day: date):
    return (model.valid_from <= day, or_(model.valid_to.is_(None), model.valid_to >= day))


def _parsed_areas(raw: object, version: CleaningPlanVersion):
    try:
        return parse_areas(raw, floor_count=version.floor_count, entrance_count=version.entrance_count)
    except AreasError as exc:  # площади под другую этажность — считаем, что их нет
        logger.warning("cleaning load: площади дома %s не подходят к плану (%s) — м² не считаются",
                       version.building_id, exc.code)
        return {}


async def report(db: AsyncSession, *, day: date, norm: int, m2_norm: int = 0) -> LoadReport:
    versions = (await db.execute(
        select(CleaningPlanVersion).join(Building, Building.id == CleaningPlanVersion.building_id)
        .where(Building.is_active.is_(True), *_valid_on(CleaningPlanVersion, day))
        .order_by(CleaningPlanVersion.building_id)
    )).scalars().all()
    stored_areas = dict((await db.execute(
        select(CleaningBuildingSettings.building_id, CleaningBuildingSettings.areas)
        .where(CleaningBuildingSettings.areas.is_not(None)))).all())
    assigned = {
        (a.building_id, a.entrance): a.user_id
        for a in (await db.execute(select(CleaningAssignment).where(*_valid_on(CleaningAssignment, day)))).scalars()
    }
    cleaners: dict[int, CleanerLoad] = {}
    unassigned: list[tuple[int, int]] = []
    for version in versions:
        try:
            items = parse_items(version.items, floor_count=version.floor_count,
                                entrance_count=version.entrance_count)
        except PlanError:
            continue
        areas = _parsed_areas(stored_areas.get(version.building_id), version)
        for entrance in range(1, version.entrance_count + 1):
            if not any(task_for(items, (), entrance=entrance, weekday=d) for d in WEEKDAYS):
                continue
            user_id = assigned.get((version.building_id, entrance))
            if user_id is None:
                unassigned.append((version.building_id, entrance))
                continue
            entry = cleaners.setdefault(user_id, CleanerLoad(norm=norm, m2_norm=m2_norm))
            per_building = entry.buildings.setdefault(version.building_id, [0] * 7)
            for weekday, floors in enumerate(floors_per_weekday(items, entrance=entrance)):
                entry.by_weekday[weekday] += floors
                per_building[weekday] += floors
            m2 = m2_per_weekday(items, areas, entrance=entrance)
            if m2 is None:
                entry.missing_areas.add(version.building_id)
            else:
                entry.m2_by_weekday = [round(a + b, 1) for a, b in zip(entry.m2_by_weekday, m2)]
    return LoadReport(cleaners=cleaners, unassigned=unassigned)
