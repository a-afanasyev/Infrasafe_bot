"""Согласие на обработку персональных данных для уже зарегистрированных.

Одобренный пользователь без согласия при первом обращении в личном чате получает
уведомление (один раз); следующее его действие засчитывается как согласие.
Работает после auth-middleware и читает уже загруженного ``data["user"]``:
у пользователя с согласием — ни одного запроса в БД.

Сбой здесь никогда не блокирует хендлер: неотправленное уведомление не
помечается и уйдёт при следующем обращении.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from uk_management_bot.config.settings import settings
from uk_management_bot.database.session import run_db
from uk_management_bot.services import pd_consent
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)


def _chat_type(event: Any) -> Optional[str]:
    message = getattr(event, "message", None)
    if message is None:
        callback = getattr(event, "callback_query", None)
        message = getattr(callback, "message", None)
    return getattr(getattr(message, "chat", None), "type", None)


def notice_text(language: str) -> str:
    company = settings.MANAGEMENT_COMPANY_NAME or get_text("pd_consent.company_default", language=language)
    return get_text("pd_consent.notice", language=language, company=html.escape(company))


async def _notify_once(bot: Any, user: Any) -> None:
    """Сначала отметка (атомарно), потом отправка: сбой БД или пачка апдейтов не
    превращаются в поток одинаковых сообщений. Не доставлено — отметка снимается."""
    if bot is None:
        logger.error("pd_consent: в data нет bot — уведомление не отправлено")
        return
    user_id = user.id

    def claim_notice(db) -> bool:
        return pd_consent.claim_notice_sync(db, user_id)

    if not await run_db(claim_notice):
        return
    try:
        await bot.send_message(user.telegram_id, notice_text(user.language or "ru"), parse_mode="HTML")
    except Exception:
        def release_notice(db) -> None:
            pd_consent.release_notice_sync(db, user_id)

        await run_db(release_notice)
        raise


async def pd_consent_middleware(handler, event: Any, data: Dict[str, Any]):
    user = data.get("user")
    if (
        user is None
        or user.pd_consent_at is not None
        or user.status != "approved"
        # Уведомление в общий чат раскрыло бы статус пользователя соседям.
        or _chat_type(event) != "private"
    ):
        return await handler(event, data)

    user_id = user.id
    try:
        notified_at = user.pd_consent_notified_at
        if notified_at is None:
            await _notify_once(data.get("bot"), user)
        else:
            if notified_at.tzinfo is None:  # sqlite отдаёт naive
                notified_at = notified_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - notified_at >= pd_consent.ACCEPT_GRACE:

                def accept(db) -> None:
                    pd_consent.accept_sync(db, user_id, pd_consent.SOURCE_CONTINUED_USE)

                await run_db(accept)
    except Exception as exc:
        logger.warning("pd_consent: шаг согласия не выполнен для user_id=%s: %s", user_id, type(exc).__name__)

    return await handler(event, data)
