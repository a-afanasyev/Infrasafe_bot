"""Сообщения бота по уборке: утро, напоминание перед концом дня, итог дня.

``collect`` решает, что и кому пора отправить, и сразу ставит отметку в
``cleaning_days`` — каждое сообщение уходит один раз за день, сколько бы тиков
ни прошло. Сама отправка (``send``) — после фиксации транзакции, best-effort.

Фото уборки бот в чате не принимает: в чате нельзя узнать, когда кадр снят.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.cleaning import CleaningDay, CleaningTask
from uk_management_bot.database.models.user import User
from uk_management_bot.services.cleaning.rules import rules_for
from uk_management_bot.services.recipients import recipients_with_action_async
from uk_management_bot.utils.business_time import business_today, business_wall_clock, fmt_date, fmt_time
from uk_management_bot.utils.datetime_utils import as_utc, utc_now
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

CLEANING_TWA_PATH = "/uk/twa/exec/cleaning"
MORNING_HOUR = 8
_UNFINISHED = ("planned", "in_progress")


@dataclass(frozen=True)
class BotMessage:
    telegram_id: int
    text: str
    language: str
    webapp: bool  # приложить кнопку открытия раздела уборки


def open_markup(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=get_text("cleaning.bot.open", language=language),
        web_app=WebAppInfo(url=f"{settings.FRONTEND_URL}{CLEANING_TWA_PATH}"))]])


def photo_in_chat_text(language: str) -> str:
    return get_text("cleaning.bot.photo_in_chat", language=language)


async def _cleaners(db: AsyncSession, day: CleaningDay, statuses: Optional[tuple[str, ...]] = None):
    """(telegram_id, язык, число заданий) по ответственным дня."""
    stmt = (select(User.telegram_id, User.language, func.count())
            .join(CleaningTask, CleaningTask.responsible_id == User.id)
            .where(CleaningTask.work_date == day.work_date, User.telegram_id.is_not(None),
                   User.bot_blocked_at.is_(None))
            .group_by(User.id, User.telegram_id, User.language).order_by(User.id))
    if statuses:
        stmt = stmt.where(CleaningTask.status.in_(statuses))
    return (await db.execute(stmt)).all()


async def _summary(db: AsyncSession, day: CleaningDay) -> list[BotMessage]:
    counts = dict((await db.execute(
        select(CleaningTask.status, func.count()).where(CleaningTask.work_date == day.work_date)
        .group_by(CleaningTask.status))).all())
    total = sum(counts.values())
    if total == 0:
        return []
    return [
        BotMessage(telegram_id=r.telegram_id, language=r.language, webapp=False, text=get_text(
            "cleaning.bot.summary", language=r.language, date=fmt_date(day.work_date), total=total,
            accepted=counts.get("accepted", 0), review=counts.get("review", 0),
            unfinished=counts.get("expired", 0) + counts.get("missed", 0), rejected=counts.get("rejected", 0)))
        for r in await recipients_with_action_async(db, "cleaning.read")
    ]


async def collect(db: AsyncSession, *, now: Optional[datetime] = None) -> list[BotMessage]:
    """Сообщения, которые пора отправить; отметки об отправке ставятся здесь же."""
    now = now or utc_now()
    messages: list[BotMessage] = []

    today = await db.get(CleaningDay, business_today(now))
    if today is not None and not today.skipped and today.closed_at is None:
        end = as_utc(today.day_end_at)
        if today.morning_sent_at is None and business_wall_clock(today.work_date, MORNING_HOUR) <= now < end:
            today.morning_sent_at = now
            messages += [BotMessage(tg, get_text("cleaning.bot.morning", language=lang or "ru", count=n),
                                    lang or "ru", True) for tg, lang, n in await _cleaners(db, today)]
        hours = int((await rules_for(db, today.work_date))["reminder_hours_before_end"])
        if today.reminded_at is None and hours > 0 and end - timedelta(hours=hours) <= now < end:
            today.reminded_at = now
            messages += [BotMessage(tg, get_text("cleaning.bot.before_end", language=lang or "ru", count=n,
                                                 time=fmt_time(end)), lang or "ru", True)
                         for tg, lang, n in await _cleaners(db, today, _UNFINISHED)]

    closed = (await db.execute(
        select(CleaningDay).where(CleaningDay.closed_at.is_not(None), CleaningDay.skipped.is_(False),
                                  CleaningDay.summary_sent_at.is_(None)).order_by(CleaningDay.work_date)
    )).scalars().all()
    for day in closed:
        day.summary_sent_at = now
        messages += await _summary(db, day)
    await db.flush()
    return messages


async def send(bot, messages: list[BotMessage]) -> int:
    """Отправить собранное; сбой одного получателя не мешает остальным."""
    sent = 0
    for message in messages:
        try:
            await bot.send_message(message.telegram_id, message.text,
                                   reply_markup=open_markup(message.language) if message.webapp else None)
            sent += 1
        except Exception as exc:  # noqa: BLE001 — текст исключения Bot API в лог не пишем
            logger.warning("cleaning: сообщение не отправлено: %s", type(exc).__name__)
    return sent
