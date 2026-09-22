"""Запрос номера телефона у пользователя из дашборда (сотрудник или житель).

Шлёт пользователю в Telegram сообщение с reply-клавиатурой `request_contact`;
дальше контакт принимает stateless-хендлер бота `handlers/phone_share.py`.

Отправка — через общий модуль API `api/telegram_send.py` (A9-P2-9: общий
клиент и таймаут, ретрай connect-сбоя, лог без токена). В отличие от notify,
результат ВОЗВРАЩАЕТСЯ: это явное действие менеджера, и «Telegram отказал»
(пользователь не запускал бота, заблокировал его) менеджер должен увидеть,
а не прочитать в логах.
"""
from __future__ import annotations

import logging

from uk_management_bot.api import telegram_send
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)


# Вердикты доставки. Прод-случай 2026-09-01: менеджер видел общее «Telegram
# delivery failed», хотя Telegram честно отвечал 403 «bot was blocked by the
# user» — причину надо доносить, иначе фича выглядит сломанной.
VERDICT_OK = telegram_send.STATUS_OK
VERDICT_BLOCKED = telegram_send.STATUS_BLOCKED   # пользователь заблокировал бота
VERDICT_NO_CHAT = telegram_send.STATUS_NO_CHAT   # пользователь ни разу не открывал чат с ботом
VERDICT_ERROR = telegram_send.STATUS_ERROR       # сеть/прочие отказы Telegram

#: Классификация ответа Telegram — одна на весь API (A9-P2-9).
_classify = telegram_send.classify


async def _send(chat_id: int, payload: dict) -> str:
    """sendMessage через общий модуль. -> вердикт доставки (VERDICT_*).

    Ретрай connect-сбоя (прод 2026-09-01: интермиттентный ConnectTimeout) и
    лог отказа — в модуле. Штамп ``bot_blocked_at`` здесь пишет
    ``record_delivery_verdict`` в сессии запроса (он же снимает штамп при
    успехе), поэтому модульная пометка отключена — без двойной записи."""
    result = await telegram_send.send_message(
        chat_id, payload["text"], reply_markup=payload.get("reply_markup"),
        mark_blocked=False,
    )
    return result.status


def raise_unless_delivered(verdict: str) -> None:
    """Вердикт → HTTP-ответ менеджеру. ОДНА точка на оба эндпоинта
    (residents и employees) — копия текстов разъехалась бы (урок BUG-170)."""
    from fastapi import HTTPException

    if verdict == VERDICT_OK:
        return
    if verdict == VERDICT_BLOCKED:
        raise HTTPException(
            status_code=409,
            detail="Пользователь заблокировал бота — попросите его "
                   "разблокировать бота и нажать Start, затем повторите")
    if verdict == VERDICT_NO_CHAT:
        raise HTTPException(
            status_code=409,
            detail="Пользователь ещё не открывал чат с ботом — попросите его "
                   "нажать Start в боте, затем повторите")
    raise HTTPException(status_code=502, detail="Telegram delivery failed")


async def record_delivery_verdict(db, user: User, verdict: str) -> None:
    """Обновить `users.bot_blocked_at` по вердикту доставки (и закоммитить).

    BLOCKED — поставить штамп (карточка покажет «Бот заблокирован»), OK —
    снять (человек разблокировал, доставка прошла). Сетевые/прочие сбои
    (`no_chat`/`error`) статус НЕ трогают: они не говорят о блокировке."""
    from datetime import datetime, timezone

    if verdict == VERDICT_BLOCKED and user.bot_blocked_at is None:
        user.bot_blocked_at = datetime.now(timezone.utc)
        await db.commit()
    elif verdict == VERDICT_OK and user.bot_blocked_at is not None:
        user.bot_blocked_at = None
        await db.commit()


async def send_phone_request(user: User) -> str:
    """Отправляет пользователю запрос поделиться контактом. -> вердикт."""
    lang = user.language or "ru"
    return await _send(user.telegram_id, {
        "text": get_text("phone_request_flow.prompt", language=lang),
        "reply_markup": {
            "keyboard": [[{
                "text": get_text("onboarding.share_contact", language=lang),
                "request_contact": True,
            }]],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        },
    })
