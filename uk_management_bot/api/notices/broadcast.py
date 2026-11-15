"""Рассылка записей раздела «Новости и уведомления» жителям в Telegram.

Очередь — те же колонки ``broadcast_*`` и та же механика, что у новостей
каналов (``api/news_watch/broadcast.py``: курсор, 429, повторы, бэкофф). Свои
здесь только правила:

* в рассылку идёт запись, которую жители уже видят (опубликована, срок
  публикации наступил, не закрыта и не истекла) — отложенная новость уходит в
  момент ``publish_at``, а не при сохранении;
* новости каналов (``source=news_watch``) этой очередью не шлются — их рассылает
  очередь ``news_items``, иначе житель получил бы сообщение дважды;
* получатели — по ``scope``: все, дворы или дома; чаты домов — только для «всех».

Текст — ввод менеджера или сотрудника: всё экранируется в точке вывода.
"""
from __future__ import annotations

import asyncio
import html
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.news_watch.broadcast import Outbox, Plan, Sender, run_outbox_cycle
from uk_management_bot.database.models.notice import (
    NOTICE_KIND_OUTAGE,
    NOTICE_SCOPE_ALL,
    NOTICE_SOURCE_NEWS_WATCH,
    NOTICE_SOURCE_STAFF,
    Notice,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.database.roles_type import roles_contain
from uk_management_bot.services.notices.audience import audience_clause
from uk_management_bot.services.notices.board import RESOURCE_ICONS
from uk_management_bot.services.notices.service import visible_clause
from uk_management_bot.utils.business_time import business_date_of, to_business

# Лимит сообщения Telegram — 4096; оставляем запас на разметку и второй язык.
_TEXT_LIMIT = 1500


def _window(notice: Notice) -> str:
    """Окно отключения на стене объекта: «18.11 10:00–14:00» / «18.11 10:00 – 20.11 14:00»."""
    if notice.starts_at is None:
        return ""
    start, end = to_business(notice.starts_at), (to_business(notice.ends_at) if notice.ends_at else None)
    if notice.all_day:
        days = start.strftime("%d.%m")
        return days if end is None or business_date_of(notice.ends_at) == start.date() else f"{days} – {end.strftime('%d.%m')}"
    if end is None:
        return start.strftime("%d.%m %H:%M")
    if end.date() == start.date():
        return f"{start.strftime('%d.%m %H:%M')}–{end.strftime('%H:%M')}"
    return f"{start.strftime('%d.%m %H:%M')} – {end.strftime('%d.%m %H:%M')}"


def _block(notice: Notice, title: str, text: str, place: str) -> str:
    icon = notice.icon or (RESOURCE_ICONS.get(notice.resource or "other", "📢") if notice.kind == NOTICE_KIND_OUTAGE else "📢")
    lines = [f"{html.escape(icon)} <b>{html.escape(title)}</b>"]
    meta = " · ".join(part for part in (_window(notice), html.escape(place)) if part)
    if meta:
        lines.append(f"🕒 {meta}")
    if text:
        lines.append(html.escape(text[:_TEXT_LIMIT]))
    return "\n".join(lines)


def render(notice: Notice) -> str:
    """Сообщение жителю: русский блок и, если заполнен, узбекский."""
    blocks = [_block(notice, notice.title_ru, notice.text_ru, notice.place_ru)]
    if (notice.title_uz or "").strip():
        blocks.append(_block(notice, notice.title_uz, notice.text_uz or "", notice.place_uz or notice.place_ru))
    return "\n\n".join(blocks)


_MANAGERS = (roles_contain(User.roles, "manager"), User.status == "approved",
             User.deleted_at.is_(None), User.bot_blocked_at.is_(None))


async def _plan(db: AsyncSession, notice: Notice) -> Plan:
    scope = notice.scope or NOTICE_SCOPE_ALL
    return Plan(
        text=render(notice),
        dm=True,
        groups=scope == NOTICE_SCOPE_ALL,
        audience=audience_clause(scope, [int(i) for i in (notice.scope_ids or [])]),
        # Отключение объявил сотрудник — менеджеры получают то же сообщение копией.
        also=_MANAGERS if notice.source == NOTICE_SOURCE_STAFF else (),
    )


NOTICES_OUTBOX = Outbox(
    model=Notice,
    label="notices",
    claimable=lambda now: (visible_clause(now), Notice.source != NOTICE_SOURCE_NEWS_WATCH),
    plan=_plan,
)


async def run_notices_broadcast_cycle(factory=None, *, send: Optional[Sender] = None,
                                      sleep=asyncio.sleep, now: Optional[datetime] = None) -> dict:
    """Один цикл рассылки записей раздела. Не бросает."""
    return await run_outbox_cycle(NOTICES_OUTBOX, factory, send=send, sleep=sleep, now=now)
