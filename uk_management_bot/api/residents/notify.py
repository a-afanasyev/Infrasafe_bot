"""Уведомления жителю о решениях менеджера (Т11).

Прямой вызов Bot API через httpx, а не aiogram: у API-процесса нет своего
экземпляра бота, и заводить его ради одного `sendMessage` незачем (тот же
приём, что в `api/registration/notify.py`).

**Никогда не поднимает исключение.** Решение менеджера уже зафиксировано в БД;
недоступный Telegram не имеет права превратить успешную операцию в 500.
Все сбои — в лог.

Текст берётся из локалей бота по языку ЖИТЕЛЯ, не менеджера. `parse_mode` не
задаётся сознательно: разнобой бота (где-то HTML, где-то Markdown) сюда не
наследуем, а обычный текст не может сломаться на скобке в адресе.
"""
from __future__ import annotations

import logging

import httpx

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

_TIMEOUT = 10


async def _send(chat_id: int, text: str, reply_markup: dict | None = None) -> None:
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
    payload: dict = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(url, json=payload)
        if response.status_code != 200:
            logger.warning(
                "Telegram отклонил уведомление жителю %s: HTTP %s",
                chat_id, response.status_code,
            )


async def _safe_send(resident: User, text: str, reply_markup: dict | None = None) -> None:
    try:
        await _send(resident.telegram_id, text, reply_markup)
    except Exception as e:  # noqa: BLE001 — best-effort, наружу не поднимаем
        logger.error("Не удалось уведомить жителя %s: %s", resident.id, e)


def _lang(resident: User) -> str:
    return resident.language or "ru"


async def notify_account_approved(resident: User) -> None:
    """Одобрение аккаунта.

    Тот же ключ и та же inline-кнопка, что у бота: текст говорит «нажмите
    кнопку ниже», и без кнопки он был бы враньём.
    """
    lang = _lang(resident)
    await _safe_send(
        resident,
        get_text("user_mgmt.handlers.application_approved_restart", language=lang),
        reply_markup={"inline_keyboard": [[{
            "text": get_text("user_mgmt.handlers.restart_bot_btn", language=lang),
            "callback_data": "restart_bot",
        }]]},
    )


async def notify_apartment_attached(resident: User, address: str) -> None:
    lang = _lang(resident)
    await _safe_send(resident, get_text(
        "web_notifications.apartment_attached", language=lang, address=address,
    ))


async def notify_binding_approved(resident: User, address: str) -> None:
    lang = _lang(resident)
    await _safe_send(resident, get_text(
        "web_notifications.binding_approved", language=lang, address=address,
    ))


async def notify_binding_rejected(resident: User, address: str, comment: str) -> None:
    lang = _lang(resident)
    await _safe_send(resident, get_text(
        "web_notifications.binding_rejected", language=lang,
        address=address, comment=comment,
    ))


async def notify_binding_removed(resident: User, address: str) -> None:
    lang = _lang(resident)
    await _safe_send(resident, get_text(
        "web_notifications.binding_removed", language=lang, address=address,
    ))
