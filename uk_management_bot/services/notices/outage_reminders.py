"""Напоминания автору незакрытого отключения: конец смены и истёкший срок.

Запись сама не закрывается (решение владельца) — бот спрашивает «включили?»
и даёт кнопку, которую обрабатывает ``handlers/outages`` (``outg:close:{id}``).
Best-effort: не бросают; текст исключения Bot API в лог не попадает.
"""
from __future__ import annotations

import html
import logging
from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from uk_management_bot.services.notices.outages import OpenOutage, open_by_author_sync
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


async def remind_after_shift_end(bot, user_id: Optional[int], *, _db=None) -> None:
    """Смена закончилась, а своё отключение не закрыто — спросить «включили?»."""
    if user_id is None or bot is None:
        return
    try:
        from uk_management_bot.database.session import run_db

        items = await run_db(lambda s: open_by_author_sync(s, user_id), db=_db)
        await send_reminders(bot, items, "remind_shift_end")
    except Exception as exc:  # noqa: BLE001
        logger.warning("outages: напоминание после смены не отправлено user=%s: %s", user_id, type(exc).__name__)
