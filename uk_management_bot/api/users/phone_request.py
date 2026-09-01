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


# Вердикты доставки. Прод-случай 2026-09-01: менеджер видел общее «Telegram
# delivery failed», хотя Telegram честно отвечал 403 «bot was blocked by the
# user» — причину надо доносить, иначе фича выглядит сломанной.
VERDICT_OK = "ok"
VERDICT_BLOCKED = "blocked"      # пользователь заблокировал бота
VERDICT_NO_CHAT = "no_chat"      # пользователь ни разу не открывал чат с ботом
VERDICT_ERROR = "error"          # сеть/прочие отказы Telegram


def _classify(status_code: int, description: str) -> str:
    """HTTP-ответ Telegram → вердикт (чистая функция, тестируется отдельно)."""
    if status_code == 200:
        return VERDICT_OK
    if status_code == 403:
        # "Forbidden: bot was blocked by the user" и родня — писать нельзя,
        # пока человек сам не разблокирует бота.
        return VERDICT_BLOCKED
    if status_code == 400 and "chat not found" in description.lower():
        return VERDICT_NO_CHAT
    return VERDICT_ERROR


async def _send(chat_id: int, payload: dict) -> str:
    """POST sendMessage. -> вердикт доставки (VERDICT_*).

    Один ретрай ТОЛЬКО на connect-сбои (прод 2026-09-01: интермиттентный
    ConnectTimeout до api.telegram.org): соединение не установлено — сообщение
    гарантированно не отправлено, дубль невозможен. Read-таймаут после
    отправки НЕ ретраим — там дубль возможен."""
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
    response = None
    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(url, json={"chat_id": chat_id, **payload})
            break
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            logger.warning("Запрос телефона: connect-сбой к Telegram для %s "
                           "(попытка %s): %s", chat_id, attempt,
                           describe_http_error(e))
            if attempt == 2:
                return VERDICT_ERROR
        except Exception as e:  # noqa: BLE001 — сеть, наружу описание без URL
            logger.error("Запрос телефона: Telegram недоступен для %s: %s",
                         chat_id, describe_http_error(e))
            return VERDICT_ERROR
    if response.status_code != 200:
        # description безопасен для лога (в отличие от текста httpx-исключений
        # он не несёт URL с токеном) и называет причину.
        try:
            description = response.json().get("description", "")
        except Exception:  # noqa: BLE001 — не-JSON тело
            description = ""
        logger.warning("Запрос телефона: Telegram отклонил сообщение %s: HTTP %s (%s)",
                       chat_id, response.status_code, description)
        return _classify(response.status_code, description)
    return VERDICT_OK


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
