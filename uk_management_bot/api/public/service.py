"""Сервис-слой публичного борда (AUD5-ARCH-2 волна 2, ARCH-05a-канон).

Module-level async функции чтения агрегатов. Сборка payload'а, проекция
статусов наружу и TTL-кэш — в router.py.
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.shift import Shift

logger = logging.getLogger(__name__)


async def status_counts_raw(db: AsyncSession) -> dict[str, int]:
    """GROUP BY по статусам заявок — сырые счётчики без проекции наружу."""
    counts_result = await db.execute(
        select(RequestModel.status, func.count())
        .group_by(RequestModel.status)
    )
    return {status: count for status, count in counts_result.all()}


async def pipeline_rows(db: AsyncSession, *, status: str, limit: int):
    """Узкая проекция активных заявок одного статуса — без персональных полей."""
    rows_result = await db.execute(
        select(RequestModel.category, RequestModel.status, RequestModel.created_at)
        .where(RequestModel.status == status)
        .order_by(RequestModel.created_at.desc())
        .limit(limit)
    )
    return rows_result.all()


async def active_executor_count(db: AsyncSession) -> int:
    """Число distinct-исполнителей на активной смене."""
    exec_result = await db.execute(
        select(func.count(func.distinct(Shift.user_id))).where(
            Shift.status == "active",
            Shift.user_id.isnot(None),
        )
    )
    return exec_result.scalar() or 0


async def avg_resolution_hours(
    db: AsyncSession, *, closed_statuses: list[str], period_start: datetime
) -> Optional[float]:
    """Среднее assigned→completed в часах по закрытым за период; None без данных
    или если БД не умеет epoch-extraction (sqlite сьюта)."""
    try:
        avg_res_result = await db.execute(
            select(
                func.avg(
                    func.extract("epoch", RequestModel.completed_at - RequestModel.assigned_at) / 3600
                )
            ).where(
                RequestModel.status.in_(closed_statuses),
                RequestModel.completed_at >= period_start,
                RequestModel.completed_at.isnot(None),
                RequestModel.assigned_at.isnot(None),
            )
        )
        avg_res_scalar = avg_res_result.scalar()
        return float(avg_res_scalar) if avg_res_scalar is not None else None
    except (OperationalError, ProgrammingError) as e:
        logger.warning("DB doesn't support epoch extraction: %s", e)
        return None


async def avg_efficiency(db: AsyncSession, *, since: datetime) -> Optional[float]:
    """Средний efficiency_score смен, начатых с `since`."""
    eff_result = await db.execute(
        select(func.avg(Shift.efficiency_score)).where(
            Shift.start_time >= since,
            Shift.efficiency_score.isnot(None),
        )
    )
    eff_scalar = eff_result.scalar()
    return float(eff_scalar) if eff_scalar is not None else None
