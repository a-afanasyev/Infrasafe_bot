"""Смена статуса учётной записи (blocked/approved) — общая для API «Сотрудники»
и домена «Жители» (AUD7-ARCH-02: перенесено из api/shifts/service/employees.py,
чтобы домен не импортировал HTTP-пакет)."""

from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.refresh_token import REASON_ADMIN, RefreshToken
from uk_management_bot.database.models.user import User

#: Статусы, при входе в которые все сессии аккаунта гасятся (AUTH-02, ревью
#: 2026-11-07): иначе после разблокировки оживали refresh-токены сроком до 30 дн.
SESSION_ENDING_STATUSES = frozenset({"blocked", "deleted"})


def _revoke_stmt(user_id: int):
    return (
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc), revocation_reason=REASON_ADMIN)
    )


async def revoke_user_sessions(db: AsyncSession, user_id: int) -> None:
    """Отозвать все активные refresh-токены пользователя (без commit)."""
    await db.execute(_revoke_stmt(user_id))


def revoke_user_sessions_sync(db: Session, user_id: int) -> None:
    """Синхронный близнец для бот-путей (без commit)."""
    db.execute(_revoke_stmt(user_id))


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
    if value in SESSION_ENDING_STATUSES:
        await revoke_user_sessions(db, user.id)
    if not commit:
        await db.flush()
        return {"entity": user, "event": None, "payload": None}
    await db.commit()
    return None
