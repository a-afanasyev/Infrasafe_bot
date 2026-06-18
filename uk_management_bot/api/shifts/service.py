"""Async data-access service for the shifts/employees API (ARCH-05a, PR-27).

Весь прямой ORM/data-access слой роутера `api/shifts/router.py` вынесен сюда:
запросы (`select`/`db.execute`/`db.scalar`), мутации (`db.add`/`commit`/
`refresh`/`delete`/`flush`) и конструирование ORM-объектов. Роутер остаётся
тонким HTTP-слоем (auth-deps, парсинг запроса, сериализация ответа, HTTP-
исключения для 404/403/409/422).

Функции принимают `db: AsyncSession` + plain-параметры и возвращают ORM-объекты
или примитивы; маппинг в response-схемы и raise HTTPException — в роутере.
AST-гейт `tests/api/test_shifts_router_inventory.py` фиксирует отсутствие
прямого ORM в роутере на нуле.
"""

import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_template import ShiftTemplate
from uk_management_bot.database.models.shift_transfer import ShiftTransfer
from uk_management_bot.database.models.user import User


# «Возвращена» (канон cutover PR3+4) — активная (ждёт разбора менеджером);
# до cutover кодировалась как «Исполнено», поэтому добавлена рядом с ним для
# сохранения прежней классификации (наружу проецируется как «Исполнено»).
ACTIVE_REQUEST_STATUSES = {"В работе", "Закуп", "Уточнение", "Выполнена", "Исполнено", "Возвращена"}


def _escape_like(value: str) -> str:
    """Escape SQL LIKE wildcards % _ \\ to prevent injection."""
    return re.sub(r'([%_\\])', r'\\\1', value)


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------

async def list_employees(
    db: AsyncSession,
    *,
    specialization: Optional[str],
    has_active_shift: Optional[bool],
    search: Optional[str],
    role: Optional[str],
    verification_status: Optional[str],
    limit: int,
    offset: int,
) -> tuple[list[User], dict[int, int]]:
    """Return (users, {user_id: active_shift_id}) for the employees list."""
    query = select(User).where(
        or_(
            User.role == "executor",
            User.roles.like('%"executor"%'),
        ),
        User.deleted_at.is_(None),
    )

    if specialization:
        query = query.where(User.specialization.like(f'%{_escape_like(specialization)}%'))

    if search:
        search_term = f"%{_escape_like(search)}%"
        query = query.where(
            or_(
                User.first_name.ilike(search_term),
                User.last_name.ilike(search_term),
                User.phone.ilike(search_term),
            )
        )
    if verification_status:
        query = query.where(User.verification_status == verification_status)
    if role:
        query = query.where(User.roles.like(f'%"{_escape_like(role)}"%'))

    if has_active_shift is True:
        active_shift_subq = (
            select(Shift.user_id)
            .where(Shift.status == "active")
            .scalar_subquery()
        )
        query = query.where(User.id.in_(active_shift_subq))
    elif has_active_shift is False:
        active_shift_subq = (
            select(Shift.user_id)
            .where(Shift.status == "active")
            .scalar_subquery()
        )
        query = query.where(User.id.not_in(active_shift_subq))

    result = await db.execute(query.offset(offset).limit(limit))
    users = result.scalars().all()

    user_ids = [u.id for u in users]
    active_shifts: dict[int, int] = {}
    if user_ids:
        shift_result = await db.execute(
            select(Shift.user_id, Shift.id)
            .where(Shift.status == "active", Shift.user_id.in_(user_ids))
        )
        for uid, sid in shift_result.all():
            active_shifts[uid] = sid

    return list(users), active_shifts


async def create_employee(
    db: AsyncSession,
    *,
    first_name: str,
    last_name: str,
    phone: str,
    role: str,
    specializations: Optional[list[str]],
    status: str,
) -> User:
    """Create an employee row directly from the web dashboard."""
    import time as _time
    import json as _json

    # Generate a negative placeholder telegram_id (real Telegram IDs are always positive)
    placeholder_tid = -abs(int(_time.time() * 1000))

    roles_list = [role]
    user = User(
        telegram_id=placeholder_tid,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        role=role,
        roles=_json.dumps(roles_list),
        active_role=role,
        specialization=_json.dumps(specializations) if specializations else None,
        status=status,
        verification_status="verified" if status == "approved" else "pending",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def set_user_verification(db: AsyncSession, user: User, value: str) -> User:
    """Persist a verification_status change (verified/rejected)."""
    user.verification_status = value
    await db.commit()
    await db.refresh(user)
    return user


async def set_user_status(db: AsyncSession, user: User, value: str) -> None:
    """Persist a status change (blocked/approved) — no refresh needed."""
    user.status = value
    await db.commit()


async def count_active_requests(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        select(func.count()).select_from(Request).where(
            Request.executor_id == user_id,
            Request.status.in_(ACTIVE_REQUEST_STATUSES),
        )
    )
    return result.scalar() or 0


async def soft_delete_employee(
    db: AsyncSession,
    *,
    user: User,
    reassign_to: Optional[int],
    reason: str,
    deleted_by_id: int,
    active_count: int,
) -> None:
    """Reassign active requests (if any), soft-delete the user, end active shifts.

    Validation of reassign target (existence / not-deleted) is left to the
    caller via `get_user`; this performs the writes within the handler tx.
    """
    if reassign_to is not None and active_count > 0:
        # SSOT-кластер #1, PR2d: переброска executor_id активных заявок через
        # allowlist-слой async_assignment_service (обновляет и активный
        # RequestAssignment), а не сырым ORM. Без commit — общая tx хендлера
        # (soft-delete + завершение смен) коммитится ниже.
        from uk_management_bot.services.async_assignment_service import AsyncAssignmentService
        _assignment_svc = AsyncAssignmentService(db)
        active_requests_result = await db.execute(
            select(Request).where(
                Request.executor_id == user.id,
                Request.status.in_(ACTIVE_REQUEST_STATUSES),
            )
        )
        for req in active_requests_result.scalars().all():
            await _assignment_svc.reassign_executor(req.request_number, reassign_to)

    # Soft-delete the user
    user.deleted_at = datetime.now(timezone.utc)
    user.deleted_by = deleted_by_id
    user.deletion_reason = reason
    user.status = "deleted"

    # End any active shift
    active_shifts_result = await db.execute(
        select(Shift).where(Shift.user_id == user.id, Shift.status.in_(["active", "paused"]))
    )
    for shift in active_shifts_result.scalars().all():
        shift.status = "completed"
        shift.end_time = datetime.now(timezone.utc)

    await db.commit()


async def get_employee_with_stats(
    db: AsyncSession, user_id: int
) -> Optional[tuple[User, Optional[Shift], int, int, Optional[float]]]:
    """Return (employee, active_shift, total_shifts, total_completed, rating).

    Returns None when the employee does not exist.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    emp = result.scalar_one_or_none()
    if not emp:
        return None

    shift_result = await db.execute(
        select(Shift).where(Shift.user_id == user_id, Shift.status == "active")
    )
    active_shift_obj = shift_result.scalar_one_or_none()

    total_result = await db.execute(
        select(func.count(Shift.id)).where(Shift.user_id == user_id)
    )
    total_shifts = total_result.scalar() or 0

    completed_result = await db.execute(
        select(func.count(Shift.id)).where(Shift.user_id == user_id, Shift.status == "completed")
    )
    total_completed = completed_result.scalar() or 0

    rating_result = await db.execute(
        select(func.avg(Shift.quality_rating)).where(
            Shift.user_id == user_id,
            Shift.status == "completed",
            Shift.quality_rating.isnot(None),
        )
    )
    rating = rating_result.scalar()

    return emp, active_shift_obj, total_shifts, total_completed, rating


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
                User.role == "executor",
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


async def list_transfers(
    db: AsyncSession, *, limit: int, offset: int
) -> list[tuple[ShiftTransfer, Optional[User], Optional[User]]]:
    """Return [(transfer, from_user, to_user)] for active transfers."""
    from_user = aliased(User)
    to_user = aliased(User)

    result = await db.execute(
        select(ShiftTransfer, from_user, to_user)
        .join(from_user, ShiftTransfer.from_executor_id == from_user.id)
        .outerjoin(to_user, ShiftTransfer.to_executor_id == to_user.id)
        .where(ShiftTransfer.status.in_(["pending", "assigned"]))
        .order_by(ShiftTransfer.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.all())


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


async def load_users_map(db: AsyncSession, user_ids: list[int]) -> dict[int, User]:
    users_map: dict[int, User] = {}
    u_res = await db.execute(select(User).where(User.id.in_(user_ids)))
    for u in u_res.scalars().all():
        users_map[u.id] = u
    return users_map


async def create_shifts_from_template(
    db: AsyncSession, *, tmpl: ShiftTemplate, user_ids: list[int],
    start_dt: datetime, end_dt: datetime,
) -> list[Shift]:
    created_shifts = []
    for uid in user_ids:
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


# ---------------------------------------------------------------------------
# Transfers
# ---------------------------------------------------------------------------

async def get_transfer_for_update(db: AsyncSession, transfer_id: int) -> Optional[ShiftTransfer]:
    result = await db.execute(
        select(ShiftTransfer).where(ShiftTransfer.id == transfer_id).with_for_update()
    )
    return result.scalar_one_or_none()


async def get_shift_for_update(db: AsyncSession, shift_id: int) -> Optional[Shift]:
    result = await db.execute(
        select(Shift).where(Shift.id == shift_id).with_for_update()
    )
    return result.scalar_one_or_none()


async def approve_transfer(
    db: AsyncSession, *, transfer: ShiftTransfer, to_executor_id: int,
) -> None:
    """Mark transfer 'assigned' and reassign its shift to the new executor."""
    transfer.status = "assigned"
    transfer.to_executor_id = to_executor_id
    transfer.assigned_at = datetime.now(timezone.utc)

    the_shift = await get_shift_for_update(db, transfer.shift_id)
    if the_shift:
        the_shift.user_id = to_executor_id


async def reject_transfer(
    db: AsyncSession, *, transfer: ShiftTransfer,
) -> Optional[Shift]:
    """Mark transfer 'rejected' and restore original executor on its shift.

    Returns the shift if found (None when the shift is gone so the caller can
    emit the original warning).
    """
    transfer.status = "rejected"
    the_shift = await get_shift_for_update(db, transfer.shift_id)
    if the_shift:
        the_shift.user_id = transfer.from_executor_id
    return the_shift


def cancel_transfer(transfer: ShiftTransfer) -> None:
    transfer.status = "cancelled"


async def commit_and_refresh_transfer(db: AsyncSession, transfer: ShiftTransfer) -> None:
    await db.commit()
    await db.refresh(transfer)


async def resolve_transfer_users(
    db: AsyncSession, transfer: ShiftTransfer
) -> tuple[Optional[User], Optional[User]]:
    from_user_result = await db.execute(select(User).where(User.id == transfer.from_executor_id))
    from_user = from_user_result.scalar_one_or_none()

    to_user = None
    if transfer.to_executor_id:
        to_user_result = await db.execute(select(User).where(User.id == transfer.to_executor_id))
        to_user = to_user_result.scalar_one_or_none()
    return from_user, to_user


# ---------------------------------------------------------------------------
# Single shift read/write
# ---------------------------------------------------------------------------

async def get_shift(db: AsyncSession, shift_id: int) -> Optional[Shift]:
    result = await db.execute(select(Shift).where(Shift.id == shift_id))
    return result.scalar_one_or_none()


async def find_overlapping_shift_for_update(
    db: AsyncSession, *, user_id: int, start_time: datetime, end_time: datetime,
    exclude_shift_id: Optional[int] = None, lock: bool = True,
) -> Optional[Shift]:
    """Return an active/planned shift overlapping [start_time, end_time), or None."""
    query = select(Shift).where(
        Shift.user_id == user_id,
        Shift.status.in_(["active", "planned"]),
        Shift.start_time < end_time,
        Shift.end_time > start_time,
    )
    if exclude_shift_id is not None:
        query = query.where(Shift.id != exclude_shift_id)
    if lock:
        query = query.with_for_update()
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def create_shift(db: AsyncSession, *, body) -> Shift:
    shift = Shift(
        user_id=body.user_id,
        start_time=body.start_time,
        end_time=body.end_time,
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
