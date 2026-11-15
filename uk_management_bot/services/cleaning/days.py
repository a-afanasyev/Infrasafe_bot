"""Задания дня: генерация из действовавших версий и закрытие дня.

Обе операции идемпотентны через ``cleaning_days`` и не зависят от момента запуска:
генерация берёт версию плана, назначения и настройки, действовавшие НА ДАТУ;
закрытие смотрит на снимок конца дня ``day_end_at``. Поэтому их можно звать и
по расписанию, и лениво из API, и после простоя — результат один.

Транзакцию фиксирует вызывающий.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.cleaning import (
    CleaningAssignment,
    CleaningDay,
    CleaningPlanVersion,
    CleaningTask,
)
from uk_management_bot.services.cleaning.planning import PlanError, parse_items, task_for
from uk_management_bot.services.cleaning.rules import day_end_at, rules_for
from uk_management_bot.services.cleaning.transitions import move
from uk_management_bot.utils.business_time import business_today
from uk_management_bot.utils.datetime_utils import as_utc, utc_now

logger = logging.getLogger(__name__)

# Итог закрытия дня для незавершённых заданий.
_CLOSE_TO = {"planned": "missed", "in_progress": "expired"}


def _valid_on(model, day: date):
    return (model.valid_from <= day, or_(model.valid_to.is_(None), model.valid_to >= day))


async def _claim_day(db: AsyncSession, row: CleaningDay) -> bool:
    """Занять маркер дня; False — день уже занял другой вызов."""
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        return False
    return True


async def ensure_tasks(db: AsyncSession, day: date, *, now: Optional[datetime] = None) -> None:
    """Создать задания бизнес-даты ``day``, если они ещё не созданы."""
    if await db.get(CleaningDay, day) is not None:
        return
    now = now or utc_now()
    rules = await rules_for(db, day)
    too_old = day < business_today(now) - timedelta(days=int(rules["backfill_days"]))
    marker = CleaningDay(work_date=day, day_end_at=day_end_at(day, rules), rules_version=rules.version,
                         skipped=too_old, closed_at=now if too_old else None)
    if not await _claim_day(db, marker) or too_old:
        return

    versions = (await db.execute(
        select(CleaningPlanVersion).join(Building, Building.id == CleaningPlanVersion.building_id)
        .where(Building.is_active.is_(True), *_valid_on(CleaningPlanVersion, day))
    )).scalars().all()
    assigned = {
        (a.building_id, a.entrance): a.user_id
        for a in (await db.execute(
            select(CleaningAssignment).where(*_valid_on(CleaningAssignment, day))
        )).scalars()
    }
    for version in versions:
        try:
            items = parse_items(version.items, floor_count=version.floor_count,
                                entrance_count=version.entrance_count)
        except PlanError as exc:  # версия прошла проверку при сохранении; битая — не роняем день
            logger.error("cleaning: версия плана %s не разобрана: %s", version.id, exc.code)
            continue
        for entrance in range(1, version.entrance_count + 1):
            task = task_for(items, version.extra_points or (), entrance=entrance, weekday=day.weekday())
            if task is None:
                continue
            db.add(CleaningTask(
                building_id=version.building_id, entrance=entrance, work_date=day,
                plan_version_id=version.id, works=list(task.works), slots_required=list(task.slots),
                responsible_id=assigned.get((version.building_id, entrance)),
            ))
    await db.flush()


async def close_days(db: AsyncSession, *, now: Optional[datetime] = None) -> None:
    """Закрыть дни, у которых конец дня плюс отсрочка уже прошли."""
    now = now or utc_now()
    open_days = (await db.execute(
        select(CleaningDay).where(CleaningDay.closed_at.is_(None), CleaningDay.skipped.is_(False))
        .order_by(CleaningDay.work_date).with_for_update()
    )).scalars().all()
    for day in open_days:
        rules = await rules_for(db, day.work_date)
        if now < as_utc(day.day_end_at) + timedelta(minutes=int(rules["close_grace_minutes"])):
            continue
        tasks = (await db.execute(
            select(CleaningTask).where(CleaningTask.work_date == day.work_date,
                                       CleaningTask.status.in_(tuple(_CLOSE_TO)))
            .with_for_update()
        )).scalars().all()
        for task in tasks:
            await move(db, task, _CLOSE_TO[task.status], kind="day_closed", rules_version=day.rules_version)
        day.closed_at = now
    await db.flush()


async def tick(db: AsyncSession, *, now: Optional[datetime] = None) -> None:
    """Догенерировать последние дни (включая сегодня) и закрыть истёкшие."""
    now = now or utc_now()
    today = business_today(now)
    backfill = int((await rules_for(db, today))["backfill_days"])
    for back in range(backfill, -1, -1):
        await ensure_tasks(db, today - timedelta(days=back), now=now)
    await close_days(db, now=now)
