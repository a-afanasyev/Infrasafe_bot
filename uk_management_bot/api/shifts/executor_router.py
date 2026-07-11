import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.shifts import service
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.services.redis_pubsub import publish_shift_event, publish_request_event

logger = logging.getLogger(__name__)

router = APIRouter()

# Service error-key → HTTP status (зеркалит менеджерский /reassign-маппинг).
_TRANSFER_ERROR_STATUS = {
    "shift_not_found": status.HTTP_404_NOT_FOUND,
    "transfer_not_found": status.HTTP_404_NOT_FOUND,
    "not_your_shift": status.HTTP_403_FORBIDDEN,
    "not_your_transfer": status.HTTP_403_FORBIDDEN,
    "transfer_already_exists": status.HTTP_409_CONFLICT,
    "overlap": status.HTTP_409_CONFLICT,
    "wrong_status": status.HTTP_409_CONFLICT,
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ShiftOut(BaseModel):
    id: int
    user_id: Optional[int]
    start_time: Optional[str]
    end_time: Optional[str]
    status: str
    notes: Optional[str]

    class Config:
        from_attributes = True


class StartShiftBody(BaseModel):
    notes: Optional[str] = None


class CreateTransferBody(BaseModel):
    shift_id: int
    reason: str
    comment: Optional[str] = None
    urgency_level: str = "normal"


class RespondTransferBody(BaseModel):
    action: str  # "accept" | "reject"


class TransferOut(BaseModel):
    id: int
    shift_id: int
    status: str
    reason: str
    urgency_level: str
    comment: Optional[str]
    from_executor_id: int
    to_executor_id: Optional[int]
    from_executor_name: Optional[str]
    to_executor_name: Optional[str]
    # "outgoing" — инициировал текущий исполнитель; "incoming" — ему назначена.
    direction: str
    # true → текущий исполнитель может принять/отклонить (assigned + получатель).
    can_respond: bool
    shift_start_time: Optional[str]
    created_at: Optional[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _shift_out(shift: Shift) -> ShiftOut:
    return ShiftOut(
        id=shift.id,
        user_id=shift.user_id,
        start_time=shift.start_time.isoformat() if shift.start_time else None,
        end_time=shift.end_time.isoformat() if shift.end_time else None,
        status=shift.status,
        notes=shift.notes,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/current", response_model=Optional[ShiftOut])
async def get_current_shift(
    user: User = Depends(require_roles("executor")),
    db: AsyncSession = Depends(get_db),
):
    """Returns the current active shift for the authenticated executor, or null.

    APIFE-1: an executor may legitimately hold several active shifts at once
    (bot-core allows one employee to cover multiple specializations — see
    services/shift_service.py). "Current" is therefore the most recent active
    shift, selected deterministically; scalar_one_or_none() here would raise
    MultipleResultsFound → 500.
    """
    result = await db.execute(
        select(Shift)
        .where(Shift.user_id == user.id, Shift.status == "active")
        .order_by(Shift.start_time.desc(), Shift.id.desc())
        .limit(1)
    )
    shift = result.scalars().first()
    if shift is None:
        return None
    return _shift_out(shift)


@router.get("/me", response_model=list[ShiftOut])
async def get_my_shifts(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_roles("executor")),
    db: AsyncSession = Depends(get_db),
):
    """Returns list of the authenticated executor's shifts (all statuses), ordered by start_time desc."""
    result = await db.execute(
        select(Shift)
        .where(Shift.user_id == user.id)
        .order_by(Shift.start_time.desc())
        .limit(limit)
    )
    shifts = result.scalars().all()
    return [_shift_out(s) for s in shifts]


@router.post("/start", response_model=ShiftOut, status_code=status.HTTP_201_CREATED)
async def start_shift(
    body: StartShiftBody,
    user: User = Depends(require_roles("executor")),
    db: AsyncSession = Depends(get_db),
):
    """Creates a new active shift for the authenticated executor."""
    now = datetime.now(timezone.utc)
    shift = Shift(
        user_id=user.id,
        status="active",
        start_time=now,
        notes=body.notes,
    )
    db.add(shift)
    await db.commit()
    await db.refresh(shift)
    return _shift_out(shift)


@router.post("/{shift_id}/end", response_model=ShiftOut)
async def end_shift(
    shift_id: int,
    user: User = Depends(require_roles("executor")),
    db: AsyncSession = Depends(get_db),
):
    """Ends a specific active shift belonging to the authenticated executor."""
    result = await db.execute(select(Shift).where(Shift.id == shift_id))
    shift = result.scalar_one_or_none()

    if shift is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift not found")
    if shift.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your shift")
    if shift.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Shift is not active (current status: {shift.status})",
        )

    shift.end_time = datetime.now(timezone.utc)
    shift.status = "completed"
    await db.commit()
    await db.refresh(shift)
    return _shift_out(shift)


# ---------------------------------------------------------------------------
# Transfers (TWA PR-T1): исполнитель инициирует передачу своей смены и
# принимает/отклоняет назначенную ему. Менеджерское назначение — на дашборде
# (`/api/v2/shifts/transfers/{id}/handle`), сюда не дублируется.
# ---------------------------------------------------------------------------

def _executor_name(user: Optional[User]) -> Optional[str]:
    if user is None:
        return None
    name = " ".join(p for p in (user.first_name, user.last_name) if p).strip()
    return name or (user.username or f"#{user.id}")


def _transfer_out(
    transfer, *, from_user: Optional[User], to_user: Optional[User],
    shift: Optional[Shift], me_id: int,
) -> TransferOut:
    return TransferOut(
        id=transfer.id,
        shift_id=transfer.shift_id,
        status=transfer.status,
        reason=transfer.reason,
        urgency_level=transfer.urgency_level,
        comment=transfer.comment,
        from_executor_id=transfer.from_executor_id,
        to_executor_id=transfer.to_executor_id,
        from_executor_name=_executor_name(from_user),
        to_executor_name=_executor_name(to_user),
        direction="outgoing" if transfer.from_executor_id == me_id else "incoming",
        can_respond=(transfer.status == "assigned" and transfer.to_executor_id == me_id),
        shift_start_time=shift.start_time.isoformat() if shift and shift.start_time else None,
        created_at=transfer.created_at.isoformat() if transfer.created_at else None,
    )


def _job(user: Optional[User], text: str) -> Optional[tuple[int, str]]:
    """(telegram_id, text) для уведомления, либо None если у пользователя нет tg."""
    tid = getattr(user, "telegram_id", None) if user else None
    return (tid, text) if tid else None


async def _notify_many(jobs: list[tuple[int, str]]) -> None:
    """Best-effort Telegram-рассылка через shared bot. Запускается как
    BackgroundTask ПОСЛЕ ответа — таймаут Telegram API не должен блокировать/
    валить сам запрос (раньше inline-await подвешивал POST при медленном TG).

    ВСЁ обёрнуто в try (вкл. получение бота): исключение в BackgroundTask
    пробрасывается Starlette и завалило бы ответ (в т.ч. невалидный токен в CI)."""
    if not jobs:
        return
    try:
        from uk_management_bot.services.notification_service import _get_shared_bot
        bot = _get_shared_bot()
    except Exception as e:
        logger.warning("transfer notify skipped — bot unavailable: %s", e)
        return
    for telegram_id, text in jobs:
        try:
            await bot.send_message(chat_id=telegram_id, text=text)
        except Exception as e:
            logger.warning("transfer notify failed for tg %s: %s", telegram_id, e)


@router.get("/transfers", response_model=list[TransferOut])
async def list_my_transfers(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_roles("executor")),
    db: AsyncSession = Depends(get_db),
):
    """Передачи текущего исполнителя (инициированные ИМ + назначенные ЕМУ)."""
    rows = await service.list_user_transfers(db, user_id=user.id, limit=limit, offset=offset)
    return [
        _transfer_out(tr, from_user=fu, to_user=tu, shift=sh, me_id=user.id)
        for (tr, fu, tu, sh) in rows
    ]


@router.post("/transfers", response_model=TransferOut, status_code=status.HTTP_201_CREATED)
async def create_my_transfer(
    body: CreateTransferBody,
    background: BackgroundTasks,
    user: User = Depends(require_roles("executor")),
    db: AsyncSession = Depends(get_db),
):
    """Исполнитель инициирует передачу своей смены (pending) + уведомляет менеджеров."""
    res = await service.create_transfer_web(
        db, shift_id=body.shift_id, from_executor_id=user.id,
        reason=body.reason, comment=body.comment, urgency_level=body.urgency_level,
    )
    if not res["success"]:
        err = res["error"]
        raise HTTPException(
            status_code=_TRANSFER_ERROR_STATUS.get(err, status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail=err,
        )

    transfer = res["transfer"]
    # Уведомить approved-менеджеров — в фоне (после ответа), чтобы таймаут
    # Telegram API не подвешивал POST.
    text = (
        f"🔄 Новая передача смены #{transfer.id} от {_executor_name(user)} — "
        f"ожидает назначения исполнителя (/assign_{transfer.id})."
    )
    jobs = [j for j in (_job(m, text) for m in await service.list_approved_managers(db)) if j]
    background.add_task(_notify_many, jobs)

    await publish_shift_event(
        "transfer.updated",
        _transfer_out(transfer, from_user=user, to_user=None, shift=None, me_id=user.id)
        .model_dump(mode="json"),
    )
    return _transfer_out(transfer, from_user=user, to_user=None, shift=None, me_id=user.id)


@router.post("/transfers/{transfer_id}/respond", response_model=TransferOut)
async def respond_my_transfer(
    transfer_id: int,
    body: RespondTransferBody,
    background: BackgroundTasks,
    user: User = Depends(require_roles("executor")),
    db: AsyncSession = Depends(get_db),
):
    """Получатель принимает (assigned→completed, перенос смены+заявок) или
    отклоняет (assigned→rejected) назначенную ему передачу."""
    if body.action not in ("accept", "reject"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="action must be 'accept' or 'reject'",
        )

    if body.action == "accept":
        res = await service.accept_transfer_web(db, transfer_id=transfer_id, executor_id=user.id)
    else:
        res = await service.reject_transfer_web_by_recipient(
            db, transfer_id=transfer_id, executor_id=user.id
        )

    if not res["success"]:
        err = res["error"]
        raise HTTPException(
            status_code=_TRANSFER_ERROR_STATUS.get(err, status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail=err,
        )

    transfer = res["transfer"]
    initiator = await service.get_user(db, res["from_executor_id"])
    manager = await service.get_user(db, transfer.assigned_by) if transfer.assigned_by else None

    if body.action == "accept":
        shift = res["shift"]
        # Realtime: смена сменила владельца + перенесённые заявки.
        await publish_shift_event(
            "shift.updated", {"id": shift.id, "user_id": shift.user_id, "status": shift.status}
        )
        for number in res["moved_request_numbers"]:
            await publish_request_event("request.updated", {"number": number})
        jobs = [
            _job(initiator, f"✅ Передача смены #{transfer.id} принята назначенным исполнителем."),
            _job(manager, f"✅ Передача смены #{transfer.id} принята исполнителем."),
        ]
    else:
        jobs = [
            _job(initiator, f"❌ Передача смены #{transfer.id} отклонена назначенным исполнителем."),
            _job(manager, f"❌ Передача смены #{transfer.id} отклонена получателем."),
        ]
    background.add_task(_notify_many, [j for j in jobs if j])

    await publish_shift_event(
        "transfer.updated",
        _transfer_out(transfer, from_user=initiator, to_user=user, shift=None, me_id=user.id)
        .model_dump(mode="json"),
    )
    return _transfer_out(transfer, from_user=initiator, to_user=user, shift=None, me_id=user.id)
