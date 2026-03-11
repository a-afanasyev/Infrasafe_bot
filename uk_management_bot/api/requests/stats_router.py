from datetime import datetime, timedelta, timezone, date as date_type
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User

router = APIRouter()

CLOSED_STATUSES = ["Выполнена", "Исполнено", "Принято", "Отменена"]


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
    request_number: str
    category: str
    status: str
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

    now_utc = datetime.now(timezone.utc)
    period_start = now_utc - timedelta(days=days)

    # --- by_day: created counts per day ---
    created_by_day_result = await db.execute(
        select(func.date(Request.created_at), func.count())
        .where(Request.created_at >= period_start)
        .group_by(func.date(Request.created_at))
    )
    created_map: dict[str, int] = {
        str(row[0]): row[1] for row in created_by_day_result.all()
    }

    # --- by_day: closed counts per day ---
    closed_by_day_result = await db.execute(
        select(func.date(Request.completed_at), func.count())
        .where(
            Request.completed_at.isnot(None),
            Request.completed_at >= period_start,
        )
        .group_by(func.date(Request.completed_at))
    )
    closed_map: dict[str, int] = {
        str(row[0]): row[1] for row in closed_by_day_result.all()
    }

    # Build full day list (one entry per day)
    by_day: list[DayStats] = []
    for i in range(days):
        day = (period_start + timedelta(days=i)).date()
        day_str = str(day)
        by_day.append(DayStats(
            date=day_str,
            created=created_map.get(day_str, 0),
            closed=closed_map.get(day_str, 0),
        ))

    # --- by_category ---
    cat_result = await db.execute(
        select(Request.category, func.count())
        .where(Request.created_at >= period_start)
        .group_by(Request.category)
    )
    by_category: dict[str, int] = {row[0]: row[1] for row in cat_result.all() if row[0]}

    # --- by_status: open requests only (not in CLOSED_STATUSES) ---
    status_result = await db.execute(
        select(Request.status, func.count())
        .where(Request.status.not_in(CLOSED_STATUSES))
        .group_by(Request.status)
    )
    by_status: dict[str, int] = {row[0]: row[1] for row in status_result.all() if row[0]}

    # --- top_executors ---
    exec_result = await db.execute(
        select(
            Request.executor_id,
            func.count().label("completed"),
            func.avg(
                func.extract("epoch", Request.completed_at - Request.assigned_at) / 3600
            ).label("avg_hours"),
        )
        .where(
            Request.status.in_(CLOSED_STATUSES),
            Request.completed_at >= period_start,
            Request.executor_id.isnot(None),
        )
        .group_by(Request.executor_id)
        .order_by(func.count().desc())
        .limit(10)
    )
    exec_rows = exec_result.all()

    # Batch-load executor users
    exec_user_ids = [row[0] for row in exec_rows]
    exec_users_map: dict[int, User] = {}
    if exec_user_ids:
        u_result = await db.execute(select(User).where(User.id.in_(exec_user_ids)))
        for u in u_result.scalars().all():
            exec_users_map[u.id] = u

    top_executors: list[ExecutorStat] = []
    for row in exec_rows:
        uid, completed, avg_h = row[0], row[1], row[2]
        u = exec_users_map.get(uid)
        name = None
        if u:
            name = f"{u.first_name or ''} {u.last_name or ''}".strip() or None
        top_executors.append(ExecutorStat(
            user_id=uid,
            name=name,
            completed=completed,
            avg_hours=float(avg_h) if avg_h is not None else None,
            score=None,
        ))

    # --- recent_actions: last 20 requests ---
    recent_result = await db.execute(
        select(Request.request_number, Request.category, Request.status, Request.created_at)
        .order_by(Request.created_at.desc())
        .limit(20)
    )
    recent_actions: list[ActivityItem] = [
        ActivityItem(
            request_number=row[0],
            category=row[1],
            status=row[2],
            created_at=row[3],
        )
        for row in recent_result.all()
    ]

    # --- total_requests ---
    total_result = await db.execute(
        select(func.count()).where(Request.created_at >= period_start)
    )
    total_requests: int = total_result.scalar() or 0

    # --- avg_resolution_hours ---
    avg_res_result = await db.execute(
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
    avg_res_scalar = avg_res_result.scalar()
    avg_resolution_hours: Optional[float] = float(avg_res_scalar) if avg_res_scalar is not None else None

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
