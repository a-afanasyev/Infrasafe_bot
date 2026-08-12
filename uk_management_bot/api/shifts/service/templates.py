"""Shift templates: CRUD шаблонов и массовое создание смен из шаблона
(AUD5-ARCH-3 волна 5, block-move из api/shifts/service.py — код
байт-в-байт)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_template import ShiftTemplate

from .lifecycle import (
    ShiftOverlapError,
    find_overlapping_shift_for_update,
    lock_user_shift_scope,
)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

async def list_templates(db: AsyncSession, *, limit: int, offset: int) -> list[ShiftTemplate]:
    result = await db.execute(
        select(ShiftTemplate)
        .where(ShiftTemplate.is_active == True)  # noqa: E712
        .order_by(ShiftTemplate.id.asc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_template(db: AsyncSession, template_id: int) -> Optional[ShiftTemplate]:
    result = await db.execute(select(ShiftTemplate).where(ShiftTemplate.id == template_id))
    return result.scalar_one_or_none()


async def create_template(db: AsyncSession, *, body) -> ShiftTemplate:
    tmpl = ShiftTemplate(
        name=body.name,
        description=body.description,
        start_hour=body.start_hour,
        start_minute=body.start_minute,
        duration_hours=body.duration_hours,
        required_specializations=body.required_specializations or [],
        min_executors=body.min_executors,
        max_executors=body.max_executors,
        default_max_requests=body.default_max_requests,
        days_of_week=body.days_of_week or [],
        auto_create=body.auto_create,
        default_shift_type=body.default_shift_type,
        priority_level=body.priority_level,
        recurrence_mode=body.recurrence_mode,
        cycle_days_on=body.cycle_days_on,
        cycle_days_off=body.cycle_days_off,
        cycle_anchor_date=body.cycle_anchor_date,
        is_active=True,
    )
    db.add(tmpl)
    await db.commit()
    await db.refresh(tmpl)
    return tmpl


async def update_template(db: AsyncSession, *, tmpl: ShiftTemplate, fields: dict) -> ShiftTemplate:
    for field, value in fields.items():
        setattr(tmpl, field, value)
    await db.commit()
    await db.refresh(tmpl)
    return tmpl


async def soft_delete_template(db: AsyncSession, *, tmpl: ShiftTemplate) -> None:
    tmpl.is_active = False
    await db.commit()


async def get_active_template(db: AsyncSession, template_id: int) -> Optional[ShiftTemplate]:
    result = await db.execute(
        select(ShiftTemplate).where(
            ShiftTemplate.id == template_id, ShiftTemplate.is_active == True  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def create_shifts_from_template(
    db: AsyncSession, *, tmpl: ShiftTemplate, user_ids: list[int],
    start_dt: datetime, end_dt: datetime,
) -> list[Shift]:
    # APIFE-5: from-template previously inserted without any overlap check →
    # mass double-booking. Lock each user's shift scope, then reject the whole
    # batch (all-or-nothing) if any user already overlaps the window.
    #
    # sorted(set(...)): (1) dedup — a duplicated uid ([5, 5]) would otherwise
    # self-overlap (siblings aren't checked against each other) → double-book;
    # (2) canonical lock order — advisory locks acquired in a globally consistent
    # order so two concurrent batches over intersecting users can't AB-BA deadlock.
    unique_ids = sorted(set(user_ids))
    conflicts: list[int] = []
    for uid in unique_ids:
        await lock_user_shift_scope(db, uid)
        if await find_overlapping_shift_for_update(
            db, user_id=uid, start_time=start_dt, end_time=end_dt, lock=False
        ):
            conflicts.append(uid)
    if conflicts:
        raise ShiftOverlapError(conflicts)

    created_shifts = []
    for uid in unique_ids:
        shift = Shift(
            user_id=uid,
            start_time=start_dt,
            end_time=end_dt,
            # planned_* mirror start/end so the bot schedule (which reads
            # planned_start_time/planned_end_time) shows real times, not "??:??".
            planned_start_time=start_dt,
            planned_end_time=end_dt,
            status="planned",
            shift_type=tmpl.default_shift_type,
            max_requests=tmpl.default_max_requests,
            priority_level=tmpl.priority_level,
            shift_template_id=tmpl.id,
            specialization_focus=tmpl.required_specializations,
            current_request_count=0,
            completed_requests=0,
        )
        db.add(shift)
        await db.flush()
        created_shifts.append(shift)

    await db.commit()
    for s in created_shifts:
        await db.refresh(s)
    return created_shifts
