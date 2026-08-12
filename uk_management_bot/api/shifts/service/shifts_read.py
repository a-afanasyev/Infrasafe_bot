"""Shifts read side: списки/расписание/статистика смен, загрузка users-map,
точечное чтение смены (AUD5-ARCH-3 волна 5, block-move из
api/shifts/service.py — код байт-в-байт)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_transfer import ShiftTransfer
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import legacy_role_filter


# ---------------------------------------------------------------------------
# Shifts CRUD
# ---------------------------------------------------------------------------

async def list_shifts(
    db: AsyncSession,
    *,
    status: Optional[str],
    shift_type: Optional[str],
    user_id: Optional[int],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    limit: int,
    offset: int,
) -> tuple[list[Shift], dict[int, User]]:
    """Return (shifts, {user_id: User}) for the shifts list."""
    query = select(Shift)
    if status:
        query = query.where(Shift.status == status)
    if shift_type:
        query = query.where(Shift.shift_type == shift_type)
    if user_id:
        query = query.where(Shift.user_id == user_id)
    if date_from:
        query = query.where(Shift.start_time >= date_from)
    if date_to:
        query = query.where(Shift.start_time <= date_to)

    result = await db.execute(query.order_by(Shift.start_time.desc()).offset(offset).limit(limit))
    shifts = list(result.scalars().all())

    users_map = await _load_users_for_shifts(db, shifts)
    return shifts, users_map


async def get_schedule(
    db: AsyncSession,
    *,
    date_from: datetime,
    date_to: datetime,
) -> tuple[list[Shift], dict[int, User]]:
    """Return (shifts, {user_id: User}) overlapping [date_from, date_to)."""
    # Overlap filter (not start_time-only): a shift belongs on every day it
    # spans, so a 24h/overnight shift shows on both its start and end day.
    # Ended shift overlaps [date_from, date_to) iff start < date_to AND end > date_from.
    # Open shifts (end_time NULL — unknown end) keep the old start-in-range
    # behaviour so a long-ago open shift doesn't leak into every future day.
    result = await db.execute(
        select(Shift)
        .where(
            Shift.start_time < date_to,
            or_(
                Shift.end_time > date_from,
                and_(Shift.end_time.is_(None), Shift.start_time >= date_from),
            ),
        )
        .order_by(Shift.start_time.asc())
    )
    shifts = list(result.scalars().all())

    users_map = await _load_users_for_shifts(db, shifts)
    return shifts, users_map


async def _load_users_for_shifts(db: AsyncSession, shifts: list[Shift]) -> dict[int, User]:
    uids = list({s.user_id for s in shifts if s.user_id})
    users_map: dict[int, User] = {}
    if uids:
        u_result = await db.execute(select(User).where(User.id.in_(uids)))
        for u in u_result.scalars().all():
            users_map[u.id] = u
    return users_map


async def get_stats(db: AsyncSession, *, period_start: datetime,
                    today_start: datetime, today_end: datetime) -> dict:
    """Aggregate dashboard stats. Caller passes pre-computed period boundaries."""
    active_count_result = await db.execute(
        select(func.count(Shift.id)).where(Shift.status == "active")
    )
    active_shifts = active_count_result.scalar() or 0

    active_exec_result = await db.execute(
        select(func.count(func.distinct(Shift.user_id))).where(
            Shift.status == "active", Shift.user_id.isnot(None)
        )
    )
    active_executors = active_exec_result.scalar() or 0

    total_exec_result = await db.execute(
        select(func.count(User.id)).where(
            User.status == "approved",
            or_(
                legacy_role_filter("executor"),
                User.roles.like('%"executor"%'),
            ),
        )
    )
    total_executors = total_exec_result.scalar() or 0

    eff_result = await db.execute(
        select(func.avg(Shift.efficiency_score)).where(
            Shift.start_time >= period_start,
            Shift.efficiency_score.isnot(None),
        )
    )
    avg_efficiency = eff_result.scalar()

    today_result = await db.execute(
        select(func.count(Shift.id)).where(
            Shift.start_time >= today_start,
            Shift.start_time <= today_end,
        )
    )
    shifts_today = today_result.scalar() or 0

    pending_result = await db.execute(
        select(func.count(ShiftTransfer.id)).where(
            ShiftTransfer.status.in_(["pending", "assigned"])
        )
    )
    pending_transfers = pending_result.scalar() or 0

    return {
        "active_shifts": active_shifts,
        "active_executors": active_executors,
        "total_executors": total_executors,
        "avg_efficiency": avg_efficiency,
        "shifts_today": shifts_today,
        "pending_transfers": pending_transfers,
    }


async def load_users_map(db: AsyncSession, user_ids: list[int]) -> dict[int, User]:
    users_map: dict[int, User] = {}
    u_res = await db.execute(select(User).where(User.id.in_(user_ids)))
    for u in u_res.scalars().all():
        users_map[u.id] = u
    return users_map


# ---------------------------------------------------------------------------
# Single shift read/write
# ---------------------------------------------------------------------------

async def get_shift(db: AsyncSession, shift_id: int) -> Optional[Shift]:
    result = await db.execute(select(Shift).where(Shift.id == shift_id))
    return result.scalar_one_or_none()
