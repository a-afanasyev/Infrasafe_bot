from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.requests import stats_service
from uk_management_bot.database.models.user import User

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class DayStats(BaseModel):
    date: str
    created: int
    closed: int


class ExecutorStat(BaseModel):
    user_id: int
    name: Optional[str]
    completed: int
    avg_hours: Optional[float]
    score: Optional[float]


class ActivityItem(BaseModel):
    event_type: str  # derived from request status: 'created', 'assigned', 'completed', 'cancelled'
    request_number: str
    executor_name: Optional[str]  # from assigned executor
    created_at: datetime


class RequestStatsOut(BaseModel):
    by_day: list[DayStats]
    by_category: dict[str, int]
    by_status: dict[str, int]
    top_executors: list[ExecutorStat]
    recent_actions: list[ActivityItem]
    total_requests: int
    avg_resolution_hours: Optional[float]
    avg_satisfaction: Optional[float]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=RequestStatsOut)
async def get_request_stats(
    period: str = Query("7d"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    # Parse period
    days = 7
    if period.endswith("d"):
        try:
            days = int(period[:-1])
        except ValueError:
            days = 7
    days = max(1, min(days, 365))

    now_utc = datetime.now(timezone.utc)
    period_start = now_utc - timedelta(days=days)

    # --- by_day: created + closed counts per day ---
    created_map: dict[str, int] = {
        str(row[0]): row[1] for row in await stats_service.created_by_day(db, period_start=period_start)
    }
    closed_map: dict[str, int] = {
        str(row[0]): row[1] for row in await stats_service.closed_by_day(db, period_start=period_start)
    }

    # Build full day list (one entry per day, including today)
    by_day: list[DayStats] = []
    for i in range(days + 1):
        day = (period_start + timedelta(days=i)).date()
        day_str = str(day)
        by_day.append(DayStats(
            date=day_str,
            created=created_map.get(day_str, 0),
            closed=closed_map.get(day_str, 0),
        ))

    # --- by_category ---
    # FS-04: нормализуем legacy RU-лейблы к канон-EN-ключу в Python и схлопываем
    # дубли (напр. «Сантехника»+«plumbing» → один plumbing), иначе аналитика
    # двоит дольки. Defense-in-depth: корректно и до миграции данных.
    from uk_management_bot.keyboards.requests import resolve_category_key
    by_category: dict[str, int] = {}
    for raw, count in await stats_service.count_by_category(db, period_start=period_start):
        if not raw:
            continue
        key = resolve_category_key(raw)
        by_category[key] = by_category.get(key, 0) + count

    # --- by_status: open requests only (not in CLOSED_STATUSES), scoped to period ---
    by_status: dict[str, int] = {
        row[0]: row[1]
        for row in await stats_service.count_by_status(db, period_start=period_start)
        if row[0]
    }

    # --- top_executors ---
    # First, get top executors by completed count (no epoch extraction here)
    exec_rows = await stats_service.top_executors_counts(db, period_start=period_start)

    # Compute avg_hours per executor separately to isolate epoch extraction
    exec_ids = [row[0] for row in exec_rows]
    avg_hours_map = await stats_service.top_executors_avg_hours(
        db, executor_ids=exec_ids, period_start=period_start
    )

    # Batch-load executor users
    exec_users_map: dict[int, User] = {
        u.id: u for u in await stats_service.load_users_by_ids(db, ids=exec_ids)
    }

    top_executors: list[ExecutorStat] = []
    for row in exec_rows:
        uid, completed = row[0], row[1]
        u = exec_users_map.get(uid)
        name = None
        if u:
            name = f"{u.first_name or ''} {u.last_name or ''}".strip() or None
        top_executors.append(ExecutorStat(
            user_id=uid,
            name=name,
            completed=completed,
            avg_hours=avg_hours_map.get(uid),
            score=None,
        ))

    # --- recent_actions: last 20 requests, scoped to period ---
    STATUS_TO_EVENT = {
        'new': 'created', 'pending': 'created',
        'assigned': 'assigned', 'in_progress': 'assigned',
        'completed': 'completed',
        'cancelled': 'cancelled', 'rejected': 'cancelled',
    }
    recent_actions: list[ActivityItem] = [
        ActivityItem(
            event_type=STATUS_TO_EVENT.get(row.status, 'created'),
            request_number=str(row.request_number),
            executor_name=f"{row.first_name or ''} {row.last_name or ''}".strip() or None,
            created_at=row.created_at,
        )
        for row in await stats_service.recent_actions(db, period_start=period_start)
    ]

    # --- total_requests ---
    total_requests: int = await stats_service.total_requests(db, period_start=period_start)

    # --- avg_resolution_hours ---
    avg_resolution_hours: Optional[float] = await stats_service.avg_resolution_hours(
        db, period_start=period_start
    )

    return RequestStatsOut(
        by_day=by_day,
        by_category=by_category,
        by_status=by_status,
        top_executors=top_executors,
        recent_actions=recent_actions,
        total_requests=total_requests,
        avg_resolution_hours=avg_resolution_hours,
        avg_satisfaction=None,
    )
