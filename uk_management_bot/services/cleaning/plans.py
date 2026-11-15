"""Версии плана уборки дома: сохранение и просмотр.

Версия неизменяема. Сохранение создаёт новую с началом действия завтра и
закрывает действующую сегодняшним днём; версию, которая ещё не начала
действовать, заменяет. Прошлое не правится — задание любого дня воспроизводимо.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.cleaning import CleaningPlanVersion, CleaningTask
from uk_management_bot.services.cleaning.planning import (
    FLOOR_WORKS,
    PlanError,
    effective,
    floor_coverage,
    parse_items,
)
from uk_management_bot.utils.business_time import business_today
from uk_management_bot.utils.datetime_utils import utc_now

_POINT_RE = re.compile(r"[a-z_]{1,30}")
MAX_EXTRA_POINTS = 10


@dataclass(frozen=True)
class PlanView:
    current: Optional[CleaningPlanVersion]   # действует сегодня
    upcoming: Optional[CleaningPlanVersion]  # начнёт действовать позже
    uncovered: dict[str, list[int]]          # работа → этажи, которые не моются ни разу в неделю
    snapshot_mismatch: bool                  # этажность/подъезды дома изменились после сохранения


def _check_points(extra_points: object) -> list[str]:
    if (not isinstance(extra_points, list) or len(extra_points) > MAX_EXTRA_POINTS
            or not all(isinstance(p, str) and _POINT_RE.fullmatch(p) for p in extra_points)
            or len(set(extra_points)) != len(extra_points)):
        raise PlanError("bad_extra_points")
    return list(extra_points)


async def _lock_building(db: AsyncSession, building_id: int) -> Building:
    building = (await db.execute(
        select(Building).where(Building.id == building_id, Building.is_active.is_(True)).with_for_update()
    )).scalar_one_or_none()
    if building is None:
        raise PlanError("building_not_found")
    return building


async def save_plan(db: AsyncSession, *, building_id: int, items: object, extra_points: object,
                    actor_id: Optional[int], now: Optional[datetime] = None) -> CleaningPlanVersion:
    """Новая версия плана дома, действует с завтрашней бизнес-даты."""
    building = await _lock_building(db, building_id)
    parsed = parse_items(items, floor_count=building.floor_count, entrance_count=building.entrance_count)
    if not parsed:
        raise PlanError("empty_plan")
    points = _check_points(extra_points)

    today = business_today(now or utc_now())
    tomorrow = today + timedelta(days=1)
    await db.execute(delete(CleaningPlanVersion).where(
        CleaningPlanVersion.building_id == building_id, CleaningPlanVersion.valid_from >= tomorrow))
    running = (await db.execute(
        select(CleaningPlanVersion).where(
            CleaningPlanVersion.building_id == building_id,
            or_(CleaningPlanVersion.valid_to.is_(None), CleaningPlanVersion.valid_to >= tomorrow))
    )).scalars().all()
    for version in running:
        version.valid_to = today

    version = CleaningPlanVersion(
        building_id=building_id, valid_from=tomorrow, items=items, extra_points=points,
        floor_count=building.floor_count, entrance_count=building.entrance_count, created_by=actor_id)
    db.add_all([version, AuditLog(user_id=actor_id, action="cleaning.plan.save", details={
        "building_id": building_id, "valid_from": tomorrow.isoformat(), "items": items, "extra_points": points})])
    await db.flush()
    return version


async def plan_view(db: AsyncSession, building_id: int, *, now: Optional[datetime] = None) -> PlanView:
    today = business_today(now or utc_now())
    building = await db.get(Building, building_id)
    if building is None:
        raise PlanError("building_not_found")
    versions = (await db.execute(
        select(CleaningPlanVersion).where(CleaningPlanVersion.building_id == building_id)
        .order_by(CleaningPlanVersion.valid_from)
    )).scalars().all()
    current = effective(versions, today)
    upcoming = next((v for v in versions if v.valid_from > today), None)
    shown = upcoming or current
    uncovered: dict[str, list[int]] = {}
    mismatch = False
    if shown is not None:
        parsed = parse_items(shown.items, floor_count=shown.floor_count, entrance_count=shown.entrance_count)
        for kind in FLOOR_WORKS:
            if any(item.work_kind == kind for item in parsed):
                gaps = [f for f, n in floor_coverage(parsed, kind, floor_count=shown.floor_count,
                                                         entrance_count=shown.entrance_count).items() if n == 0]
                if gaps:
                    uncovered[kind] = gaps
        mismatch = (shown.floor_count, shown.entrance_count) != (building.floor_count, building.entrance_count)
    return PlanView(current=current, upcoming=upcoming, uncovered=uncovered, snapshot_mismatch=mismatch)


async def tasks_of(db: AsyncSession, building_id: int, day: date) -> list[CleaningTask]:
    return list((await db.execute(
        select(CleaningTask).where(CleaningTask.building_id == building_id, CleaningTask.work_date == day)
        .order_by(CleaningTask.entrance)
    )).scalars())
