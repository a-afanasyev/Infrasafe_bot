"""Shift lifecycle core: ShiftOverlapError, FOR UPDATE/advisory-lock,
overlap-проверка, create/update/delete/end смены (AUD5-ARCH-3 волна 5,
block-move из api/shifts/service.py — код байт-в-байт)."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.shift import Shift


class ShiftOverlapError(Exception):
    """One or more users already have a shift overlapping the requested window.

    Carries the conflicting user_ids so the router can surface them in a 409.
    """

    def __init__(self, conflicts: list[int]):
        self.conflicts = conflicts
        super().__init__(f"overlapping shifts for users: {conflicts}")


async def get_shift_for_update(db: AsyncSession, shift_id: int) -> Optional[Shift]:
    result = await db.execute(
        select(Shift).where(Shift.id == shift_id).with_for_update()
    )
    return result.scalar_one_or_none()


# APIFE-11: namespace for the per-user shift advisory lock. Postgres FOR UPDATE
# locks only existing overlapping rows — it has no gap/predicate lock, so two
# concurrent inserts into an empty slot both pass the overlap check and commit
# (double-booking, reproduced with lock=True too). A per-user transaction-level
# advisory lock serializes the check-then-write across ALL manager-side shift
# mutations, making it atomic. Executor POST /start intentionally skips this so
# multi-specialization multi-active shifts stay allowed (APIFE-1).
_SHIFT_LOCK_NS = 0x5348  # "SH"


async def lock_user_shift_scope(db: AsyncSession, user_id: int) -> None:
    """Serialize all shift mutations for one user within this transaction.

    No-op off PostgreSQL (SQLite tests) — the advisory lock exists only to close
    the concurrent double-booking race, which SQLite can't exhibit anyway.
    """
    if db.bind.dialect.name != "postgresql":
        return
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :uid)"),
        {"ns": _SHIFT_LOCK_NS, "uid": int(user_id)},
    )


async def find_overlapping_shift_for_update(
    db: AsyncSession, *, user_id: int, start_time: datetime, end_time: datetime,
    exclude_shift_id: Optional[int] = None, lock: bool = True,
) -> Optional[Shift]:
    """Return an active/planned shift overlapping [start_time, end_time), or None.

    APIFE-5: an open-ended shift (end_time IS NULL, created by executor POST /start)
    models [start, +inf) and overlaps the window iff it started before it ends —
    the plain ``end_time > start_time`` predicate silently misses it (NULL > x = NULL).
    """
    query = select(Shift).where(
        Shift.user_id == user_id,
        Shift.status.in_(["active", "planned"]),
        Shift.start_time < end_time,
        or_(Shift.end_time.is_(None), Shift.end_time > start_time),
    )
    if exclude_shift_id is not None:
        query = query.where(Shift.id != exclude_shift_id)
    query = query.limit(1)
    if lock:
        query = query.with_for_update()
    result = await db.execute(query)
    # APIFE-1: caller only needs the fact of an overlap; with several overlapping
    # shifts scalar_one_or_none() would raise MultipleResultsFound → 500.
    return result.scalars().first()


async def create_shift(db: AsyncSession, *, body) -> Shift:
    shift = Shift(
        user_id=body.user_id,
        start_time=body.start_time,
        end_time=body.end_time,
        # BUG-128: planned_* обязаны зеркалить фактические времена. Бот-расписание
        # (`handlers/my_shifts.py:handle_week_schedule`) фильтрует по
        # `func.date(Shift.planned_start_time)`, поэтому без этих двух строк смена,
        # созданная менеджером в веб-дашборде, оставалась с NULL и исполнитель её
        # в «Мои смены → Расписание на неделю» не видел вообще. Два других пути
        # создания/правки (`create_shifts_from_template`, `apply_shift_update`)
        # синхронизировали их с самого начала — расходился только POST.
        planned_start_time=body.start_time,
        planned_end_time=body.end_time,
        status="active",
        shift_type=body.shift_type,
        specialization_focus=body.specialization_focus or [],
        max_requests=body.max_requests,
        priority_level=body.priority_level,
        notes=body.notes,
        current_request_count=0,
        completed_requests=0,
    )
    db.add(shift)
    await db.commit()
    await db.refresh(shift)
    return shift


async def apply_shift_update(
    db: AsyncSession, *, shift: Shift, data: dict,
) -> Shift:
    """Apply field updates to a shift, syncing planned_*, commit + refresh."""
    for field, value in data.items():
        setattr(shift, field, value)

    # The bot schedule reads planned_*; keep it in sync when actual times change
    # (mirrors create_from_template, which sets planned_* = actual start/end).
    if "start_time" in data:
        shift.planned_start_time = shift.start_time
    if "end_time" in data:
        shift.planned_end_time = shift.end_time

    await db.commit()
    await db.refresh(shift)
    return shift


async def delete_shift(db: AsyncSession, *, shift: Shift) -> None:
    await db.delete(shift)
    await db.commit()


async def end_shift(db: AsyncSession, *, shift: Shift) -> Shift:
    shift.end_time = datetime.now(timezone.utc)
    shift.status = "completed"
    await db.commit()
    await db.refresh(shift)
    return shift
