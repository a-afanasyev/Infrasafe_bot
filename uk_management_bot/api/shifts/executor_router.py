import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.shifts import service
from uk_management_bot.services import shift_lifecycle
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.services.redis_pubsub import publish_shift_event, publish_request_event
from uk_management_bot.utils.telegram_client import SEND_TIMEOUT
from uk_management_bot.utils.user_names import display_name

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
    background: BackgroundTasks,
    user: User = Depends(require_roles("executor")),
    db: AsyncSession = Depends(get_db),
):
    """Creates a new active shift for the authenticated executor."""
    # A9-P1-2: правило бота (services/shift_lifecycle) — идущая planned-смена
    # активируется, ad-hoc создаётся только если такой нет (докстринг выше
    # уходит в OpenAPI-снапшот — контракт не меняем). Audit — в той же tx;
    # исполнитель и ops-канал уведомляются после ответа.
    shift = await shift_lifecycle.start_shift_async(db, user, notes=body.notes)
    await db.commit()
    await db.refresh(shift)
    background.add_task(_notify_shift, _shift_notify_payload(user, shift, started=True))
    return _shift_out(shift)


@router.post("/{shift_id}/end", response_model=ShiftOut)
async def end_shift(
    shift_id: int,
    background: BackgroundTasks,
    user: User = Depends(require_roles("executor")),
    db: AsyncSession = Depends(get_db),
):
    """Ends a specific active shift belonging to the authenticated executor."""
    # FOR UPDATE: двойной тап / бот+TWA — второй увидит completed → 409,
    # без второго audit и уведомления (зеркало my_shifts._end_shift).
    result = await db.execute(select(Shift).where(Shift.id == shift_id).with_for_update())
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

    await shift_lifecycle.end_shift_async(db, user, shift)
    await db.commit()
    await db.refresh(shift)
    background.add_task(_notify_shift, _shift_notify_payload(user, shift, started=False))
    background.add_task(_remind_open_tasks, user.id)
    return _shift_out(shift)


async def _remind_open_tasks(user_id: int) -> None:
    """Фаза 4: незакрытые заявки после конца смены — личка исполнителю (как
    в боте). Best-effort: смена уже завершена, сбой здесь её не касается."""
    try:
        from uk_management_bot.services.executor_done_prompt import remind_after_shift_end
        from uk_management_bot.services.notification_service import _get_shared_bot
        await remind_after_shift_end(_get_shared_bot(), user_id)
    except Exception as e:
        logger.warning("open-tasks reminder skipped: %s", type(e).__name__)


def _shift_notify_payload(user: User, shift: Shift, *, started: bool):
    """Сбой билдера не валит уже закоммиченный старт/стоп (как AUD8-CODE-01 в боте)."""
    try:
        return shift_lifecycle.shift_notify_payload(user, shift, started=started)
    except Exception:
        logger.warning("shift notify: не удалось собрать уведомление (shift=%s)",
                       shift.id, exc_info=True)
        return None


async def _notify_shift(payload) -> None:
    """Best-effort уведомление о старте/конце смены (исполнитель + ops-канал) —
    те же тексты и адресаты, что у бота. BackgroundTask после ответа; всё в
    try (вкл. получение бота) — см. `_notify_many`."""
    if not payload:
        return
    try:
        from uk_management_bot.services.notification_service import _get_shared_bot
        bot = _get_shared_bot()
    except Exception as e:
        logger.warning("shift notify skipped — bot unavailable: %s", e)
        return
    await shift_lifecycle.send_shift_notify(bot, payload)


# ---------------------------------------------------------------------------
# Transfers (TWA PR-T1): исполнитель инициирует передачу своей смены и
# принимает/отклоняет назначенную ему. Менеджерское назначение — на дашборде
# (`/api/v2/shifts/transfers/{id}/handle`), сюда не дублируется.
# ---------------------------------------------------------------------------

def _executor_name(user: Optional[User]) -> Optional[str]:
    """Имя с фолбэком: подпись в TransferOut пустой быть не может.

    REFACTOR-133: фолбэк теперь общий (`@username`, иначе `ID{telegram_id}`).
    Строка видима в ответе API (`TransferOut`), поэтому менялась отдельным
    решением, а не заодно с технической правкой.
    """
    return display_name(user)


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
            await bot.send_message(
                chat_id=telegram_id, text=text, request_timeout=SEND_TIMEOUT
            )
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
