"""Нагрузка уборщиц в этажах: сколько этажей по плану приходится на каждый день недели.

Считается из версий планов и назначений, действующих на дату; меняется план или
привязка — меняется и отчёт. Точки без этажей (кабина лифта) в нагрузку не входят.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.cleaning import CleaningAssignment, CleaningPlanVersion
from uk_management_bot.services.cleaning.planning import WEEKDAYS, PlanError, PlanItem, parse_items, task_for


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
    def overloaded(self) -> bool:
        return self.norm > 0 and self.peak > self.norm


@dataclass(frozen=True)
class LoadReport:
    cleaners: dict[int, CleanerLoad]
    unassigned: list[tuple[int, int]]  # (дом, подъезд) с работами по плану, но без ответственного


def _valid_on(model, day: date):
    return (model.valid_from <= day, or_(model.valid_to.is_(None), model.valid_to >= day))


async def report(db: AsyncSession, *, day: date, norm: int) -> LoadReport:
    versions = (await db.execute(
        select(CleaningPlanVersion).join(Building, Building.id == CleaningPlanVersion.building_id)
        .where(Building.is_active.is_(True), *_valid_on(CleaningPlanVersion, day))
        .order_by(CleaningPlanVersion.building_id)
    )).scalars().all()
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
        for entrance in range(1, version.entrance_count + 1):
            if not any(task_for(items, (), entrance=entrance, weekday=d) for d in WEEKDAYS):
                continue
            user_id = assigned.get((version.building_id, entrance))
            if user_id is None:
                unassigned.append((version.building_id, entrance))
                continue
            entry = cleaners.setdefault(user_id, CleanerLoad(norm=norm))
            per_building = entry.buildings.setdefault(version.building_id, [0] * 7)
            for weekday, floors in enumerate(floors_per_weekday(items, entrance=entrance)):
                entry.by_weekday[weekday] += floors
                per_building[weekday] += floors
    return LoadReport(cleaners=cleaners, unassigned=unassigned)
