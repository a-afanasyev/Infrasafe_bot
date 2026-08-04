"""Предикат «исполнитель сейчас на смене» — единый источник (sync + async).

Раньше расходилось: раннер workflow считал сменой просто `status==active`, а
UI/пул — `status==active И start_time<=now И (end_time IS NULL OR end_time>=now)`.
Из-за расхождения claim мог пройти там, где пул исполнителю не виден. Единое
условие живёт здесь (`_on_shift_filter`), две тонкие обёртки sync/async.

`now` по умолчанию — `utc_now()` (ARCH-137 фаза A, owner-decision принят):
наивный default был корректен лишь пока рантайм-зона процесса — UTC, и ровно
здесь смена `TZ` раскалывала бы sync (psycopg2 читает session TimeZone) и
async (asyncpg трактует naive как UTC) на величину смещения.
"""

from __future__ import annotations

from datetime import datetime
from uk_management_bot.utils.datetime_utils import utc_now
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.utils.constants import SHIFT_STATUS_ACTIVE


def effective_shift_time():
    """FS-06/FS-07: единое «эффективное время смены» для UI-чтений.

    Плановые смены живут на `planned_start_time`, ad-hoc (через «Принять смену»)
    — только на `start_time` (`planned_start_time` = NULL). Вьюхи «Текущие смены»
    и «История смен» раньше фильтровали/показывали по `planned_start_time` → не
    видели ad-hoc-смены (расхождение с «Моя смена»/«История» на `start_time`).
    `COALESCE(planned_start_time, start_time)` сводит оба типа к одному полю.
    NB: НЕ заменяет `_on_shift_filter` (предикат «на смене сейчас» для claim-пула).
    """
    return func.coalesce(Shift.planned_start_time, Shift.start_time)


def on_shift_window(now: datetime):
    """«Смена активна в момент `now`» БЕЗ привязки к исполнителю.

    Вынесено отдельно, чтобы вопрос «кто сейчас на смене» решался ОДНИМ
    запросом. Раньше на него отвечали циклом `is_on_shift_now_sync` по каждому
    пользователю — то же условие, но N запросов (WR-05).
    """
    return (
        (Shift.status == SHIFT_STATUS_ACTIVE)
        & (Shift.start_time <= now)
        & or_(Shift.end_time.is_(None), Shift.end_time >= now)
    )


def _on_shift_filter(user_id: int, now: datetime):
    """Общее условие активной смены в момент `now` (для sync и async)."""
    return (Shift.user_id == user_id) & on_shift_window(now)


def is_on_shift_now_sync(db: Session, user_id: int,
                         now: Optional[datetime] = None) -> bool:
    now = now or utc_now()
    return db.query(Shift.id).filter(
        _on_shift_filter(user_id, now)).first() is not None


async def is_on_shift_now_async(db: AsyncSession, user_id: int,
                                now: Optional[datetime] = None) -> bool:
    now = now or utc_now()
    res = await db.execute(select(Shift.id).where(_on_shift_filter(user_id, now)))
    return res.first() is not None
