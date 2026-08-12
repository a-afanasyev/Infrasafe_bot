"""Web transfer flows: менеджерский reassign (REG-02) и executor-facing
передачи (TWA PR-T1) — async-зеркала бот-сервиса ShiftTransferService
(AUD5-ARCH-3 волна 5, block-move из api/shifts/service.py — код
байт-в-байт)."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_assignment import ShiftAssignment
from uk_management_bot.database.models.shift_transfer import ShiftTransfer
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import legacy_role_filter
from uk_management_bot.utils.specializations import has_required_specs
from uk_management_bot.api.dependencies import _parse_user_roles

from .employees import get_user
from .lifecycle import (
    find_overlapping_shift_for_update,
    get_shift_for_update,
    lock_user_shift_scope,
)
from .transfers import get_transfer_for_update

# REG-02: статусы заявок, переносимых вместе со сменой при переназначении
# (status-preserving). Совпадает с бот-ядром ShiftTransferService.
REASSIGN_MOVE_STATUSES = {"В работе", "Закуп", "Уточнение"}


# ---------------------------------------------------------------------------
# Manager-direct reassign (REG-02) — async-зеркало ShiftTransferService.reassign_shift
# ---------------------------------------------------------------------------

async def _move_active_requests_web(
    db: AsyncSession, shift: Shift, old_executor_id: int, new_executor_id: int,
) -> list[str]:
    """Status-preserving перенос активных заявок смены old→new (без commit).

    Скоуп: не-терминальные ShiftAssignment этой смены; fallback по
    Request.executor_id только для active-смены. Переброска — через allowlist-слой
    AsyncAssignmentService.reassign_executor. Возвращает перенесённые request_number.
    """
    from uk_management_bot.services.async_assignment_service import AsyncAssignmentService

    assignment_svc = AsyncAssignmentService(db)

    sa_result = await db.execute(
        select(ShiftAssignment).where(
            ShiftAssignment.shift_id == shift.id,
            ShiftAssignment.status.notin_(["completed", "cancelled"]),
        )
    )
    request_numbers = {row.request_number for row in sa_result.scalars().all()}

    if not request_numbers and shift.status == "active":
        fb_result = await db.execute(
            select(Request).where(
                Request.executor_id == old_executor_id,
                Request.status.in_(REASSIGN_MOVE_STATUSES),
            )
        )
        request_numbers = {r.request_number for r in fb_result.scalars().all()}

    moved: list[str] = []
    for request_number in request_numbers:
        req_result = await db.execute(
            select(Request).where(Request.request_number == request_number)
        )
        req = req_result.scalar_one_or_none()
        if req and req.status in REASSIGN_MOVE_STATUSES:
            if await assignment_svc.reassign_executor(request_number, new_executor_id):
                moved.append(request_number)
    return moved


async def reassign_shift_web(
    db: AsyncSession, *, shift_id: int, new_executor_id: int, manager_id: int,
) -> dict:
    """Прямой менеджерский reassign смены (без согласия получателя).

    Те же guards, что бот-ядро (approved/executor/спец-ия/overlap active+planned,
    не текущий владелец). Меняет `shift.user_id`, переносит активные заявки
    (status-preserving), пишет ShiftTransfer-историю, commit. Возвращает
    {success, error, moved_request_numbers, shift}. Realtime/HTTP-маппинг — в роутере.
    """
    shift = await get_shift_for_update(db, shift_id)
    if not shift:
        return {"success": False, "error": "shift_not_found"}
    # Смену без владельца / в терминальном статусе переназначать нельзя
    # (история требует from_executor_id NOT NULL; completed/cancelled нечего
    # передавать). Зеркалит bot-ядро _validate_reassign_target.
    if shift.user_id is None or shift.status not in ("planned", "active"):
        return {"success": False, "error": "shift_not_transferable"}

    new_executor = await get_user(db, new_executor_id)
    if not new_executor:
        return {"success": False, "error": "executor_not_found"}
    if new_executor.status != "approved":
        return {"success": False, "error": "not_approved"}
    if "executor" not in _parse_user_roles(new_executor):
        return {"success": False, "error": "not_executor"}
    if shift.user_id == new_executor_id:
        return {"success": False, "error": "same_executor"}
    if not has_required_specs(new_executor, shift):
        return {"success": False, "error": "spec_mismatch"}
    # Open-ended (end_time IS NULL) shift reassignment intentionally skips the
    # overlap guard: an executor may hold several open multi-spec shifts (APIFE-1).
    if shift.start_time is not None and shift.end_time is not None:
        await lock_user_shift_scope(db, new_executor_id)
        overlap = await find_overlapping_shift_for_update(
            db, user_id=new_executor_id, start_time=shift.start_time,
            end_time=shift.end_time, exclude_shift_id=shift.id, lock=True,
        )
        if overlap:
            return {"success": False, "error": "overlap"}

    old_executor_id = shift.user_id
    shift.user_id = new_executor_id
    moved = await _move_active_requests_web(db, shift, old_executor_id, new_executor_id)

    now = datetime.now(timezone.utc)
    db.add(ShiftTransfer(
        shift_id=shift.id,
        from_executor_id=old_executor_id,
        to_executor_id=new_executor_id,
        assigned_by=manager_id,
        status="completed",
        reason="manager_reassign",
        auto_assigned=True,
        assigned_at=now,
        responded_at=now,
        completed_at=now,
    ))

    await db.commit()
    await db.refresh(shift)
    return {"success": True, "error": None, "moved_request_numbers": moved, "shift": shift}


# ---------------------------------------------------------------------------
# Executor-facing transfer flow (TWA PR-T1) — async-зеркало бот-сервиса
# ShiftTransferService.{create_transfer,accept_transfer,reject_transfer}.
# ---------------------------------------------------------------------------

# Статусы, блокирующие создание новой передачи на ту же смену (зеркалит
# бот-сервис _BLOCKING_TRANSFER_STATUSES).
_BLOCKING_TRANSFER_STATUSES = ("pending", "assigned", "accepted")


async def list_approved_managers(db: AsyncSession) -> list[User]:
    """Approved-менеджеры — для best-effort уведомления о новой передаче."""
    result = await db.execute(
        select(User).where(
            legacy_role_filter("manager"),
            User.status == "approved",
        )
    )
    return list(result.scalars().all())


async def list_user_transfers(
    db: AsyncSession, *, user_id: int, limit: int, offset: int
) -> list[tuple[ShiftTransfer, Optional[User], Optional[User], Optional[Shift]]]:
    """[(transfer, from_user, to_user, shift)] передач, где user — инициатор ИЛИ получатель."""
    from_user = aliased(User)
    to_user = aliased(User)

    result = await db.execute(
        select(ShiftTransfer, from_user, to_user, Shift)
        .join(from_user, ShiftTransfer.from_executor_id == from_user.id)
        .outerjoin(to_user, ShiftTransfer.to_executor_id == to_user.id)
        .outerjoin(Shift, ShiftTransfer.shift_id == Shift.id)
        .where(
            or_(
                ShiftTransfer.from_executor_id == user_id,
                ShiftTransfer.to_executor_id == user_id,
            )
        )
        .order_by(ShiftTransfer.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.all())


async def create_transfer_web(
    db: AsyncSession, *, shift_id: int, from_executor_id: int,
    reason: str, comment: Optional[str], urgency_level: str,
) -> dict:
    """Исполнитель инициирует передачу своей смены (status=pending).

    Guards зеркалят бот-сервис: смена существует, принадлежит инициатору,
    в статусе planned/active, на неё нет активной передачи. БЕЗ уведомлений
    (их шлёт роутер после commit). Возвращает {success, error, transfer}.
    """
    shift = await get_shift_for_update(db, shift_id)
    if not shift:
        return {"success": False, "error": "shift_not_found"}
    if shift.user_id != from_executor_id:
        return {"success": False, "error": "not_your_shift"}
    if shift.status not in ("planned", "active"):
        return {"success": False, "error": "shift_not_transferable"}

    existing = await db.execute(
        select(ShiftTransfer).where(
            ShiftTransfer.shift_id == shift_id,
            ShiftTransfer.status.in_(_BLOCKING_TRANSFER_STATUSES),
        )
    )
    if existing.scalar_one_or_none():
        return {"success": False, "error": "transfer_already_exists"}

    transfer = ShiftTransfer(
        shift_id=shift_id,
        from_executor_id=from_executor_id,
        status="pending",
        reason=reason or "other",
        comment=comment or None,
        urgency_level=urgency_level or "normal",
    )
    db.add(transfer)
    await db.commit()
    await db.refresh(transfer)
    return {"success": True, "error": None, "transfer": transfer}


async def accept_transfer_web(
    db: AsyncSession, *, transfer_id: int, executor_id: int,
) -> dict:
    """Получатель принимает назначенную передачу: assigned→completed.

    Переносит владельца смены и активные заявки (status-preserving) на
    получателя. Гонка assign→accept перепроверяется (approved/executor/спец/
    overlap) — зеркалит бот-`accept_transfer`→`reassign_shift`. Запись передачи
    САМА является историей (НЕ создаём отдельную, в отличие от reassign_shift_web).
    """
    transfer = await get_transfer_for_update(db, transfer_id)
    if not transfer:
        return {"success": False, "error": "transfer_not_found"}
    if transfer.status != "assigned":
        return {"success": False, "error": "wrong_status"}
    if transfer.to_executor_id != executor_id:
        return {"success": False, "error": "not_your_transfer"}

    shift = await get_shift_for_update(db, transfer.shift_id)
    if not shift:
        return {"success": False, "error": "shift_not_found"}
    if shift.user_id is None or shift.status not in ("planned", "active"):
        return {"success": False, "error": "shift_not_transferable"}

    recipient = await get_user(db, executor_id)
    if not recipient or recipient.status != "approved" \
            or "executor" not in _parse_user_roles(recipient):
        return {"success": False, "error": "not_executor"}
    if not has_required_specs(recipient, shift):
        return {"success": False, "error": "spec_mismatch"}
    # Open-ended shift accept intentionally skips the overlap guard (APIFE-1).
    if shift.start_time is not None and shift.end_time is not None:
        await lock_user_shift_scope(db, executor_id)
        overlap = await find_overlapping_shift_for_update(
            db, user_id=executor_id, start_time=shift.start_time,
            end_time=shift.end_time, exclude_shift_id=shift.id, lock=True,
        )
        if overlap:
            return {"success": False, "error": "overlap"}

    old_executor_id = shift.user_id
    if not transfer.update_status("accepted"):
        return {"success": False, "error": "wrong_status"}
    shift.user_id = executor_id
    moved = await _move_active_requests_web(db, shift, old_executor_id, executor_id)
    transfer.update_status("completed")

    await db.commit()
    await db.refresh(transfer)
    await db.refresh(shift)
    return {
        "success": True, "error": None, "transfer": transfer, "shift": shift,
        "moved_request_numbers": moved, "from_executor_id": old_executor_id,
    }


async def reject_transfer_web_by_recipient(
    db: AsyncSession, *, transfer_id: int, executor_id: int,
) -> dict:
    """Получатель отклоняет назначенную передачу: assigned→rejected.

    Смена НЕ менялась на assign-шаге, восстанавливать нечего.
    """
    transfer = await get_transfer_for_update(db, transfer_id)
    if not transfer:
        return {"success": False, "error": "transfer_not_found"}
    if transfer.status != "assigned":
        return {"success": False, "error": "wrong_status"}
    if transfer.to_executor_id != executor_id:
        return {"success": False, "error": "not_your_transfer"}

    if not transfer.update_status("rejected"):
        return {"success": False, "error": "wrong_status"}
    await db.commit()
    await db.refresh(transfer)
    return {"success": True, "error": None, "transfer": transfer,
            "from_executor_id": transfer.from_executor_id}
