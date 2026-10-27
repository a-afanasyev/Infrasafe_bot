"""Сообщение всем, кому разрешено действие (адресаты — services/recipients)."""
from __future__ import annotations

import logging

from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

SEND_TIMEOUT = 10


async def notify_action_holders(session_factory, action_key: str, text_key: str, **params) -> int:
    """Разослать `text_key` на языке каждого получателя. Не бросает по
    получателю; возвращает число доставленных сообщений. Подстановки
    вызывающий передаёт уже экранированными (parse_mode=HTML)."""
    from uk_management_bot.services.notification_service import _get_shared_bot
    from uk_management_bot.services.recipients import recipients_with_action_async

    async with session_factory() as db:
        recipients = await recipients_with_action_async(db, action_key)
    bot = _get_shared_bot()
    delivered = 0
    for r in recipients:
        try:
            await bot.send_message(
                chat_id=r.telegram_id,
                text=get_text(text_key, language=r.language).format(**params),
                parse_mode="HTML",
                request_timeout=SEND_TIMEOUT,
            )
            delivered += 1
        except Exception as exc:  # noqa: BLE001 — по получателю, best-effort
            logger.warning("notify %s: tg=%s не отправлено: %s", text_key, r.telegram_id, exc)
    return delivered
