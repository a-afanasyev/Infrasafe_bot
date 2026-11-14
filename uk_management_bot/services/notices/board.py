"""Списки витрины из таблицы ``notices``.

Табло, главная жителей и TWA читают ``announcements`` и ``planned_works`` в
прежнем формате (services/board_config/schemas.py) — здесь эти списки
собираются из ``notices`` и подставляются в конфиг вместо хранимого JSON.

Правила показа:
* новость → «Новости»;
* отключение с окном → «Ближайшие работы» (сегодняшние и будущие);
* отключение из канала или от сотрудника — ещё и в «Новости», важным:
  оно срочное, и жители ищут его там же, где раньше (news-watch).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.notice import (
    NOTICE_KIND_NEWS,
    NOTICE_KIND_OUTAGE,
    NOTICE_SOURCE_MANUAL,
    Notice,
)
from uk_management_bot.services.board_config.schemas import (
    MAX_PLANNED_WORKS,
    AnnouncementCfg,
    LocalizedText,
    PlannedWorkCfg,
    StoredBoardConfigData,
)
from uk_management_bot.services.notices.service import visible_clause
from uk_management_bot.utils.business_time import business_date_of, to_business
from uk_management_bot.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

# Иконка по виду ресурса, если менеджер не задал свою.
RESOURCE_ICONS = {"power": "⚡", "water": "💧", "gas": "🔥", "heating": "🌡", "internet": "🌐", "other": "📢"}


def public_id(notice: Notice) -> str:
    return f"notice-{notice.id}"


def _hhmm(moment: Optional[datetime], on_day) -> str:
    """Время на стене объекта — только если момент приходится на показанный день."""
    if moment is None or business_date_of(moment) != on_day:
        return ""
    return to_business(moment).strftime("%H:%M")


def as_announcement(notice: Notice) -> AnnouncementCfg:
    published = notice.publish_at or notice.created_at
    return AnnouncementCfg(
        id=public_id(notice),
        icon=notice.icon or (RESOURCE_ICONS.get(notice.resource or "other", "") if notice.kind == NOTICE_KIND_OUTAGE else ""),
        important=bool(notice.important) or notice.kind == NOTICE_KIND_OUTAGE,
        title=LocalizedText(ru=notice.title_ru, uz=notice.title_uz),
        text=LocalizedText(ru=notice.text_ru, uz=notice.text_uz),
        # Настенное время объекта без зоны — формат поля редактора (datetime-local).
        published_at=to_business(published).replace(tzinfo=None).isoformat(timespec="seconds") if published else "",
    )


def as_planned_work(notice: Notice, now: datetime) -> Optional[PlannedWorkCfg]:
    """Отключение → строка «Ближайших работ»; уже закончившееся — None."""
    if notice.starts_at is None:
        return None
    today = business_date_of(now)
    start_day = business_date_of(notice.starts_at)
    end_day = business_date_of(notice.ends_at) if notice.ends_at else start_day
    if end_day < today:
        return None
    day = max(start_day, today)  # идущее не первый день показываем сегодняшним
    return PlannedWorkCfg(
        id=public_id(notice),
        date=day.isoformat(),
        time_from="" if notice.all_day else _hhmm(notice.starts_at, day),
        time_to="" if notice.all_day else _hhmm(notice.ends_at, day),
        title=LocalizedText(ru=notice.title_ru, uz=notice.title_uz),
        place=LocalizedText(ru=notice.place_ru, uz=notice.place_uz),
        text=LocalizedText(ru=notice.text_ru, uz=notice.text_uz),
    )


async def board_lists(db: AsyncSession, now: Optional[datetime] = None) -> tuple[list[AnnouncementCfg], list[PlannedWorkCfg]]:
    now = now or utc_now()
    # Свежие выше — порядок ленты на табло (важные вперёд выносит сам потребитель).
    rows = await db.execute(
        select(Notice).where(visible_clause(now))
        .order_by(func.coalesce(Notice.publish_at, Notice.created_at).desc(), Notice.id.desc())
    )
    announcements: list[AnnouncementCfg] = []
    works: list[PlannedWorkCfg] = []
    for notice in rows.scalars().all():
        if notice.kind == NOTICE_KIND_NEWS or notice.source != NOTICE_SOURCE_MANUAL:
            announcements.append(as_announcement(notice))
        if notice.kind == NOTICE_KIND_OUTAGE:
            work = as_planned_work(notice, now)
            if work is not None:
                works.append(work)
    works.sort(key=lambda w: (w.date, w.time_from))
    return announcements, works[:MAX_PLANNED_WORKS]


async def with_notices(db: AsyncSession, cfg: StoredBoardConfigData) -> StoredBoardConfigData:
    """Конфиг витрины с новостями и работами из ``notices``.

    Таблицы ещё нет (образ новее схемы) → списки из хранимого конфига, как до
    переноса: публичные страницы не должны падать.
    """
    try:
        announcements, works = await board_lists(db)
    except (OperationalError, ProgrammingError) as e:
        logger.warning("notices недоступна, витрина отдаёт списки из board_config: %s", e)
        return cfg
    return cfg.model_copy(update={"announcements": announcements, "planned_works": works})
