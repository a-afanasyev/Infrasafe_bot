"""AUD5-ARCH-3 волна 8 (block-move из api/shifts/router.py): web-передачи смен.

POST /transfers/{transfer_id}/handle + best-effort уведомление получателя.
Тела перенесены байт-в-байт.
"""
import logging

from fastapi import BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_roles, _parse_user_roles
from uk_management_bot.api.shifts import service
from uk_management_bot.api.shifts.schemas import HandleTransferBody, TransferOut
from uk_management_bot.database.models.user import User
from uk_management_bot.services.redis_pubsub import publish_shift_event

from ._helpers import _executor_name
from ._router import router

logger = logging.getLogger(__name__)


async def _notify_transfer_assigned(telegram_id: int, lang: str, transfer_id: int) -> None:
    """Best-effort: уведомить получателя о назначенной web-передаче с клавиатурой
    ответа. Запускается как BackgroundTask (после ответа) — сбой/таймаут TG не
    влияет на запрос."""
    try:
        from uk_management_bot.services.notification_service import _get_shared_bot
        from uk_management_bot.keyboards.shift_transfer import transfer_response_keyboard
        from uk_management_bot.utils.helpers import get_text

        await _get_shared_bot().send_message(
            chat_id=telegram_id,
            text=get_text("shift_transfer.handlers.transfer_assigned_to_you", language=lang),
            reply_markup=transfer_response_keyboard(transfer_id, lang),
        )
    except Exception as notify_err:
        logger.warning("Не удалось уведомить получателя tg %s о передаче %s: %s",
                       telegram_id, transfer_id, notify_err)


@router.post("/transfers/{transfer_id}/handle", response_model=TransferOut)
async def handle_transfer(
    transfer_id: int,
    body: HandleTransferBody,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    transfer = await service.get_transfer_for_update(db, transfer_id)
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")

    action = body.action

    if action == "approve":
        if transfer.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot approve transfer in status '{transfer.status}' — expected 'pending'",
            )
        if body.to_executor_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="to_executor_id is required for action 'approve'",
            )
        # Validate target executor exists and has executor role
        new_executor = await service.get_user(db, body.to_executor_id)
        if not new_executor:
            raise HTTPException(status_code=404, detail="Executor not found")
        has_exec_role = "executor" in _parse_user_roles(new_executor)
        if not has_exec_role:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Target user does not have executor role",
            )
        await service.approve_transfer(
            db, transfer=transfer, to_executor_id=body.to_executor_id, manager_id=_user.id
        )

    elif action == "reject":
        if transfer.status != "assigned":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot reject transfer in status '{transfer.status}' — expected 'assigned'",
            )
        the_shift = await service.reject_transfer(db, transfer=transfer)
        if the_shift is None:
            logger.warning(
                "Shift %s not found when rejecting transfer %s — shift.user_id not restored",
                transfer.shift_id, transfer.id
            )

    elif action == "cancel":
        if transfer.status not in ("pending", "assigned"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot cancel transfer in status '{transfer.status}'",
            )
        service.cancel_transfer(transfer)

    await service.commit_and_refresh_transfer(db, transfer)

    # Resolve executor names
    from_user, to_user = await service.resolve_transfer_users(db, transfer)

    transfer_out = TransferOut(
        id=transfer.id,
        shift_id=transfer.shift_id,
        from_executor_name=_executor_name(from_user),
        to_executor_name=_executor_name(to_user) if to_user else None,
        status=transfer.status,
        reason=transfer.reason,
        urgency_level=transfer.urgency_level,
        comment=transfer.comment,
        created_at=transfer.created_at,
    )

    await publish_shift_event("transfer.updated", transfer_out.model_dump(mode="json"))

    # CR-8: при web-назначении (approve) уведомить получателя в Telegram с
    # клавиатурой ответа — иначе приём передачи был недостижим (web сам не
    # шлёт уведомление, а в боте не было входа для assigned-получателя).
    # В фоне (после ответа): таймаут Telegram API не должен подвешивать запрос;
    # приём также доступен через /my_transfers в боте.
    if action == "approve" and to_user is not None and getattr(to_user, "telegram_id", None):
        background.add_task(
            _notify_transfer_assigned,
            to_user.telegram_id,
            getattr(to_user, "language", None) or "ru",
            transfer.id,
        )

    return transfer_out
