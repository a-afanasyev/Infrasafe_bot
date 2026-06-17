"""Предикат «исполнитель сейчас на смене» — единый источник (sync + async).

Раньше расходилось: раннер workflow считал сменой просто `status==active`, а
UI/пул — `status==active И start_time<=now И (end_time IS NULL OR end_time>=now)`.
Из-за расхождения claim мог пройти там, где пул исполнителю не виден. Единое
условие живёт здесь (`_on_shift_filter`), две тонкие обёртки sync/async.

`now` по умолчанию — наивный `datetime.now()` (как в UI-запросе видимости пула),
чтобы семантика окна смены совпадала со существующим прод-поведением.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.shift import Shift
from uk_management_bot.utils.constants import SHIFT_STATUS_ACTIVE


def _on_shift_filter(user_id: int, now: datetime):
    """Общее условие активной смены в момент `now` (для sync и async)."""
    return (
        (Shift.user_id == user_id)
        & (Shift.status == SHIFT_STATUS_ACTIVE)
        & (Shift.start_time <= now)
        & or_(Shift.end_time.is_(None), Shift.end_time >= now)
    )


def is_on_shift_now_sync(db: Session, user_id: int,
                         now: Optional[datetime] = None) -> bool:
    now = now or datetime.now()
    return db.query(Shift.id).filter(
        _on_shift_filter(user_id, now)).first() is not None


async def is_on_shift_now_async(db: AsyncSession, user_id: int,
                                now: Optional[datetime] = None) -> bool:
    now = now or datetime.now()
    res = await db.execute(select(Shift.id).where(_on_shift_filter(user_id, now)))
    return res.first() is not None
