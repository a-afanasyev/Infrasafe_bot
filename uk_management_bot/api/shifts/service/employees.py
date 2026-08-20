"""Employees domain: список/карточка сотрудников, активация pending-стаффа,
верификация/статусы/роли-капабилити, soft-delete (AUD5-ARCH-3 волна 5,
block-move из api/shifts/service.py — код байт-в-байт)."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.rating import Rating
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import parse_roles_safe
from uk_management_bot.utils.sql_search import (
    ci_contains_any,
    escape_like as _escape_like,
    is_postgres,
)

# Роли, считающиеся «сотрудником» (в отличие от жителя-applicant). Используются
# в фиде pending-стаффа и guard'ах активации/отклонения.
_STAFF_ROLES = frozenset({"manager", "executor", "inspector"})
# Приоритет при выборе active_role после активации (см. activate_employee).
_STAFF_ROLE_PRIORITY = ("manager", "executor", "inspector")


def _is_staff(user: User) -> bool:
    """True, если у пользователя есть хоть одна стафф-роль (manager/executor/inspector)."""
    return bool(_STAFF_ROLES & set(parse_roles_safe(user.roles)))

# «Возвращена» (канон cutover PR3+4) — активная (ждёт разбора менеджером);
# до cutover кодировалась как «Исполнено», поэтому добавлена рядом с ним для
# сохранения прежней классификации (наружу проецируется как «Исполнено»).
ACTIVE_REQUEST_STATUSES = {"В работе", "Закуп", "Уточнение", "Выполнена", "Исполнено", "Возвращена"}


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
    """Return (users, {user_id: active_shift_id}) for the employees list.

    По умолчанию список executor-scoped — им кормятся дропдауны назначения на
    смену/заявку (там допустимы только исполнители). Явный ``role`` ЗАМЕНЯЕТ этот
    scope (страница «Сотрудники» так показывает менеджеров/обходчиков по фильтру),
    а НЕ добавляется поверх executor — иначе ``role='manager'`` давал бы «executor
    И manager» и чистые менеджеры (без роли executor) никогда бы не находились.
    """
    scoped_role = role or "executor"
    query = select(User).where(
        User.roles.like(f'%"{_escape_like(scoped_role)}"%'),
        User.deleted_at.is_(None),
    )

    if specialization:
        query = query.where(User.specialization.like(f'%{_escape_like(specialization)}%'))

    if search:
        search_term = f"%{_escape_like(search)}%"
        query = query.where(
            ci_contains_any(
                (User.first_name, User.last_name, User.phone),
                search_term,
                is_postgres=is_postgres(db),
            )
        )
    if verification_status:
        query = query.where(User.verification_status == verification_status)

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


async def get_user(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def set_user_verification(db: AsyncSession, user: User, value: str) -> User:
    """Persist a verification_status change (verified/rejected)."""
    user.verification_status = value
    await db.commit()
    await db.refresh(user)
    return user


async def set_user_status(
    db: AsyncSession, user: User, value: str, *, commit: bool = True,
) -> None | dict:
    """Persist a status change (blocked/approved) — no refresh needed.

    `commit=False` (Т1) — режим для владельца транзакции снаружи (раздел
    «Жители»): только мутация + flush, возвращается `{entity, event, payload}`.
    `event=None` здесь ЛЕГАЛЕН и обязателен: смены статуса аккаунта нет в
    `_ROUTING` адресных событий, и вызывающий не должен звать для неё
    `enqueue_outbox` — тот упал бы ValueError на неизвестном событии.
    """
    user.status = value
    if not commit:
        await db.flush()
        return {"entity": user, "event": None, "payload": None}
    await db.commit()
    return None


async def set_meter_entry_role(db: AsyncSession, user: User, enabled: bool) -> User:
    """Выдать/снять роль-капабилити `resource_meter_entry` (контролёр показаний).

    Хранится строкой в user.roles (JSON). НЕ трогает active_role — это
    капабилити, а не переключаемая роль. Идемпотентна.
    """
    import json as _json

    roles = parse_roles_safe(user.roles)
    if enabled and "resource_meter_entry" not in roles:
        roles.append("resource_meter_entry")
    elif not enabled and "resource_meter_entry" in roles:
        roles.remove("resource_meter_entry")
    else:
        return user  # no-op — состояние уже соответствует
    user.roles = _json.dumps(roles)
    await db.commit()
    await db.refresh(user)
    return user


async def list_pending_staff(db: AsyncSession) -> list[User]:
    """Сотрудники (manager/executor/inspector) со `status='pending'` — очередь
    активации аккаунта в дашборде.

    Ключ — `status` (гейт доступа бота), НЕ `verification_status`. Отклонённые
    по верификации исключаются: reject-эндпоинт меняет только
    `verification_status`, оставляя `status='pending'`, иначе они бы висели в
    очереди вечно. Чистые applicant-жители (без стафф-роли) сюда не попадают.
    """
    result = await db.execute(
        select(User)
        .where(
            User.status == "pending",
            User.deleted_at.is_(None),
            User.verification_status != "rejected",
            or_(
                User.roles.like('%"manager"%'),
                User.roles.like('%"executor"%'),
                User.roles.like('%"inspector"%'),
            ),
        )
        .order_by(User.created_at)
    )
    return list(result.scalars().all())


async def activate_employee(db: AsyncSession, user: User) -> User:
    """Одобрить pending-стафф: `status`→approved (+verified, если была pending).

    Также поднимает `active_role` до стафф-роли, если она всё ещё `applicant`:
    приглашённый через бота сотрудник после `/join` остаётся с
    `active_role='applicant'` (auth_service не меняет валидную active_role), из-за
    чего меню менеджера в боте не появилось бы без ручного переключения.
    """
    user.status = "approved"
    if user.verification_status == "pending":
        user.verification_status = "verified"
    if user.active_role not in _STAFF_ROLES:
        user_roles = set(parse_roles_safe(user.roles))
        for role in _STAFF_ROLE_PRIORITY:
            if role in user_roles:
                user.active_role = role
                break
    await db.commit()
    await db.refresh(user)
    return user


async def decline_employee(db: AsyncSession, user: User) -> User:
    """Отклонить pending-стафф: `status`→blocked."""
    user.status = "blocked"
    await db.commit()
    await db.refresh(user)
    return user


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

    # APIFE-1: an executor may hold several active shifts (multi-specialization,
    # bot-core intentionally allows it). Pick the most recent deterministically;
    # scalar_one_or_none() would raise MultipleResultsFound → 500 on the card.
    # The card reflects only this freshest active shift; the aggregate counters
    # below already tolerate multiplicity.
    shift_result = await db.execute(
        select(Shift)
        .where(Shift.user_id == user_id, Shift.status == "active")
        .order_by(Shift.start_time.desc(), Shift.id.desc())
        .limit(1)
    )
    active_shift_obj = shift_result.scalars().first()

    total_result = await db.execute(
        select(func.count(Shift.id)).where(Shift.user_id == user_id)
    )
    total_shifts = total_result.scalar() or 0

    completed_result = await db.execute(
        select(func.count(Shift.id)).where(Shift.user_id == user_id, Shift.status == "completed")
    )
    total_completed = completed_result.scalar() or 0

    # Средний балл заявок исполнителя: оценки жителей (1–5) при приёмке.
    # Джойн через requests.executor_id, а не RequestAssignment — поле пишет
    # канонический движок, и оно есть у легаси-заявок без строк assignment.
    # (Раньше тут был avg(Shift.quality_rating) — колонку не пишет никто,
    # карточка всегда показывала «—».)
    rating_result = await db.execute(
        select(func.avg(Rating.rating))
        .join(Request, Request.request_number == Rating.request_number)
        .where(Request.executor_id == user_id)
    )
    rating = rating_result.scalar()
    rating = float(rating) if rating is not None else None

    return emp, active_shift_obj, total_shifts, total_completed, rating
