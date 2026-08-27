"""Запрос номера телефона у пользователя из дашборда (сотрудник или житель).

Шлёт пользователю в Telegram сообщение с reply-клавиатурой `request_contact`;
дальше контакт принимает stateless-хендлер бота `handlers/phone_share.py`.

Прямой вызов Bot API через httpx — тот же приём, что в `api/residents/notify.py`
(у API-процесса нет своего экземпляра aiogram-бота). В отличие от notify,
результат ВОЗВРАЩАЕТСЯ: это явное действие менеджера, и «Telegram отказал»
(пользователь не запускал бота, заблокировал его) менеджер должен увидеть,
а не прочитать в логах. Текст ошибки httpx в лог не пишем целиком — он несёт
URL с токеном (`describe_http_error`).
"""
from __future__ import annotations

import logging

import httpx

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.http_errors import describe_http_error

logger = logging.getLogger(__name__)

_TIMEOUT = 10


async def _send(chat_id: int, payload: dict) -> bool:
    """POST sendMessage. -> Telegram принял сообщение?"""
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(url, json={"chat_id": chat_id, **payload})
    except Exception as e:  # noqa: BLE001 — сеть, наружу только описание без URL
        logger.error("Запрос телефона: Telegram недоступен для %s: %s",
                     chat_id, describe_http_error(e))
        return False
    if response.status_code != 200:
        logger.warning("Запрос телефона: Telegram отклонил сообщение %s: HTTP %s",
                       chat_id, response.status_code)
        return False
    return True


async def send_phone_request(user: User) -> bool:
    """Отправляет пользователю запрос поделиться контактом. -> успех."""
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
