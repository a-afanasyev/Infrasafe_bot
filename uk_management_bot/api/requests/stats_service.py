"""Async data-access service for the request-stats API (ARC-06).

Весь прямой ORM/data-access слой роутера `api/requests/stats_router.py`
(`get_request_stats`) вынесен сюда: 10 агрегирующих `select`/`db.execute`.
Роутер остаётся тонким HTTP-слоем (auth-dep, парсинг периода, сборка DTO,
`resolve_category_key`-нормализация, `STATUS_TO_EVENT`-маппинг).

Функции принимают `db: AsyncSession` + plain-параметры и возвращают СЫРЫЕ
результаты (списки Row / скаляры / служебные dict), НЕ response-схемы. where-
клаузы перенесены БУКВАЛЬНО — date-фильтры неоднородны (created_at vs
completed_at), не унифицировать.

AST-гейт `tests/api/test_stats_router_inventory.py` фиксирует отсутствие
прямого ORM в роутере на нуле.
"""

import logging
from typing import Optional, Sequence

from sqlalchemy import select, func
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User

logger = logging.getLogger(__name__)

# «Возвращена» (канон cutover PR3+4): до cutover кодировалась как «Исполнено»
# и входила в closed-набор статистики; добавлена рядом для сохранения прежней
# классификации (наружу = «Исполнено» по проекции).
CLOSED_STATUSES = ["Выполнена", "Исполнено", "Возвращена", "Принято", "Отменена"]


async def created_by_day(db: AsyncSession, *, period_start) -> Sequence:
    """Строки (date, count) созданных заявок по дням за период."""
    result = await db.execute(
        select(func.date(Request.created_at), func.count())
        .where(Request.created_at >= period_start)
        .group_by(func.date(Request.created_at))
    )
    return result.all()


async def closed_by_day(db: AsyncSession, *, period_start) -> Sequence:
    """Строки (date, count) закрытых заявок по дням за период."""
    result = await db.execute(
        select(func.date(Request.completed_at), func.count())
        .where(
            Request.completed_at.isnot(None),
            Request.completed_at >= period_start,
        )
        .group_by(func.date(Request.completed_at))
    )
    return result.all()


async def count_by_category(db: AsyncSession, *, period_start) -> Sequence:
    """Сырые строки (category, count) за период — нормализация в роутере."""
    result = await db.execute(
        select(Request.category, func.count())
        .where(Request.created_at >= period_start)
        .group_by(Request.category)
    )
    return result.all()


async def count_by_status(db: AsyncSession, *, period_start) -> Sequence:
    """Строки (status, count) открытых заявок (не в CLOSED_STATUSES) за период."""
    result = await db.execute(
        select(Request.status, func.count())
        .where(
            Request.status.not_in(CLOSED_STATUSES),
            Request.created_at >= period_start,
        )
        .group_by(Request.status)
    )
    return result.all()


async def top_executors_counts(db: AsyncSession, *, period_start, limit: int = 10) -> Sequence:
    """Топ-исполнители по числу закрытых заявок: строки (executor_id, completed)."""
    result = await db.execute(
        select(
            Request.executor_id,
            func.count().label("completed"),
        )
        .where(
            Request.status.in_(CLOSED_STATUSES),
            Request.completed_at >= period_start,
            Request.executor_id.isnot(None),
        )
        .group_by(Request.executor_id)
        .order_by(func.count().desc())
        .limit(limit)
    )
    return result.all()


async def top_executors_avg_hours(
    db: AsyncSession, *, executor_ids, period_start
) -> dict[int, Optional[float]]:
    """Средние часы разрешения по исполнителям. Изолирует epoch-extraction:
    при неподдерживающей БД (OperationalError/ProgrammingError) → пустой dict.
    ⚠ Фильтр по created_at (не completed_at) — сохранено буквально из исходника.
    """
    avg_hours_map: dict[int, Optional[float]] = {}
    if not executor_ids:
        return avg_hours_map
    try:
        ah_result = await db.execute(
            select(
                Request.executor_id,
                func.avg(
                    func.extract("epoch", Request.completed_at - Request.assigned_at) / 3600
                ),
            )
            .where(
                Request.executor_id.in_(executor_ids),
                Request.completed_at.isnot(None),
                Request.assigned_at.isnot(None),
                Request.created_at >= period_start,
            )
            .group_by(Request.executor_id)
        )
        for uid, avg_h in ah_result.all():
            avg_hours_map[uid] = float(avg_h) if avg_h is not None else None
    except (OperationalError, ProgrammingError) as e:
        logger.warning("DB doesn't support epoch extraction: %s", e)
    return avg_hours_map


async def load_users_by_ids(db: AsyncSession, *, ids) -> list[User]:
    """Батч-загрузка пользователей по списку id (пустой список → [])."""
    if not ids:
        return []
    result = await db.execute(select(User).where(User.id.in_(ids)))
    return list(result.scalars().all())


async def recent_actions(db: AsyncSession, *, period_start, limit: int = 20) -> Sequence:
    """Последние заявки за период: строки (request_number, status, created_at,
    first_name, last_name) с outer-join исполнителя. Маппинг событий — в роутере.
    """
    result = await db.execute(
        select(
            Request.request_number,
            Request.status,
            Request.created_at,
            User.first_name,
            User.last_name,
        )
        .outerjoin(User, Request.executor_id == User.id)
        .where(Request.created_at >= period_start)
        .order_by(Request.created_at.desc())
        .limit(limit)
    )
    return result.all()


async def total_requests(db: AsyncSession, *, period_start) -> int:
    """Всего заявок за период."""
    result = await db.execute(
        select(func.count(Request.request_number)).where(Request.created_at >= period_start)
    )
    return result.scalar() or 0


async def avg_resolution_hours(db: AsyncSession, *, period_start) -> Optional[float]:
    """Среднее время разрешения (часы) по закрытым заявкам за период.
    Изолирует epoch-extraction: при неподдерживающей БД → None.
    """
    try:
        result = await db.execute(
            select(
                func.avg(
                    func.extract("epoch", Request.completed_at - Request.assigned_at) / 3600
                )
            )
            .where(
                Request.status.in_(CLOSED_STATUSES),
                Request.completed_at >= period_start,
                Request.completed_at.isnot(None),
                Request.assigned_at.isnot(None),
            )
        )
        scalar = result.scalar()
        return float(scalar) if scalar is not None else None
    except (OperationalError, ProgrammingError) as e:
        logger.warning("DB doesn't support epoch extraction: %s", e)
        return None
