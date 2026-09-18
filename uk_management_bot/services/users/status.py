"""Смена статуса учётной записи (blocked/approved) — общая для API «Сотрудники»
и домена «Жители» (AUD7-ARCH-02: перенесено из api/shifts/service/employees.py,
чтобы домен не импортировал HTTP-пакет)."""

from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.user import User


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
