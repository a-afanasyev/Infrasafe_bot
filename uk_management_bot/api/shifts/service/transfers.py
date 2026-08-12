"""Manager-side transfers: список активных передач, FOR UPDATE-чтение,
approve/reject/cancel, резолв участников (AUD5-ARCH-3 волна 5, block-move
из api/shifts/service.py — код байт-в-байт)."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_transfer import ShiftTransfer
from uk_management_bot.database.models.user import User

from .lifecycle import get_shift_for_update


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
# Transfers
# ---------------------------------------------------------------------------

async def get_transfer_for_update(db: AsyncSession, transfer_id: int) -> Optional[ShiftTransfer]:
    result = await db.execute(
        select(ShiftTransfer).where(ShiftTransfer.id == transfer_id).with_for_update()
    )
    return result.scalar_one_or_none()


async def approve_transfer(
    db: AsyncSession, *, transfer: ShiftTransfer, to_executor_id: int, manager_id: int,
) -> None:
    """Назначить получателя передачи (pending→assigned). ASSIGN-ONLY (REG-02).

    НЕ трогает `shift.user_id` — смена переходит к исполнителю только когда он
    ПРИМЕТ передачу в боте (`accept_transfer`). Раньше web сразу переписывал
    владельца смены, конфликтуя с unified-флоу «assign → executor accept».
    """
    transfer.status = "assigned"
    transfer.to_executor_id = to_executor_id
    transfer.assigned_by = manager_id
    transfer.assigned_at = datetime.now(timezone.utc)


async def reject_transfer(
    db: AsyncSession, *, transfer: ShiftTransfer,
) -> Optional[Shift]:
    """Отклонить передачу (assigned→rejected). Смена НЕ менялась на assign-шаге
    (REG-02), поэтому восстанавливать `shift.user_id` не нужно.

    Возвращает смену (или None, если её нет — для прежнего warning у вызывающего).
    """
    transfer.status = "rejected"
    return await get_shift_for_update(db, transfer.shift_id)


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
