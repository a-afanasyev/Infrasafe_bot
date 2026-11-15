"""Напоминания автору незакрытого отключения: конец смены и истёкший срок.

Оба шлёт тик планировщика бота (``utils/shift_scheduler``) — раз в 10 минут.

Запись сама не закрывается (решение владельца) — бот спрашивает «включили?»
и даёт кнопку, которую обрабатывает ``handlers/outages`` (``outg:close:{id}``).
Best-effort: не бросают; текст исключения Bot API в лог не попадает.
"""
from __future__ import annotations

import html
import logging
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from uk_management_bot.services.notices.outages import OpenOutage
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

CLOSE_PREFIX = "outg:close:"


def close_markup(notice_id: int, title: str, language: str) -> InlineKeyboardMarkup:
    # Текст кнопки — не HTML: экранировать нельзя, иначе житель увидит &amp;.
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=get_text("outages.btn_close", language=language, title=title)[:60],
        callback_data=f"{CLOSE_PREFIX}{notice_id}")]])


async def send_reminders(bot, items: list[OpenOutage], key: str) -> int:
    """``key`` — remind_shift_end | remind_overdue."""
    sent = 0
    for item in items:
        try:
            await bot.send_message(
                item.telegram_id,
                get_text(f"outages.{key}", language=item.language, title=html.escape(item.title(), quote=False)),
                reply_markup=close_markup(item.notice_id, item.title(), item.language), parse_mode="HTML")
            sent += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("outages: напоминание не отправлено notice=%s: %s", item.notice_id, type(exc).__name__)
    return sent
