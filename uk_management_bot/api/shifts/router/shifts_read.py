"""AUD5-ARCH-3 волна 8 (block-move из api/shifts/router.py): чтение смен.

GET ""(список) / /schedule / /stats / /transfers — статические пути, которые
обязаны регистрироваться ДО catch-all /{shift_id} (см. __init__.py).
Тела перенесены байт-в-байт.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.shifts import service
from uk_management_bot.api.shifts.schemas import ShiftBrief, ShiftStatsOut, TransferOut
from uk_management_bot.database.models.user import User

from ._helpers import _executor_name, _shift_brief
from ._router import router


# ---------------------------------------------------------------------------
# Shifts CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ShiftBrief])
async def list_shifts(
    status: Optional[str] = Query(None),
    shift_type: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    shifts, users_map = await service.list_shifts(
        db,
        status=status,
        shift_type=shift_type,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return [_shift_brief(s, users_map.get(s.user_id) if s.user_id else None) for s in shifts]


@router.get("/schedule", response_model=list[ShiftBrief])
async def get_schedule(
    date_from: datetime = Query(...),
    date_to: datetime = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="date_to must be >= date_from")
    if (date_to - date_from).days > 90:
        raise HTTPException(status_code=422, detail="Date range cannot exceed 90 days")
    shifts, users_map = await service.get_schedule(db, date_from=date_from, date_to=date_to)
    return [_shift_brief(s, users_map.get(s.user_id) if s.user_id else None) for s in shifts]


@router.get("/stats", response_model=ShiftStatsOut)
async def get_stats(
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

    from datetime import timedelta
    period_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    period_start = period_start - timedelta(days=days - 1)

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59, microsecond=999999)

    stats = await service.get_stats(
        db, period_start=period_start, today_start=today_start, today_end=today_end
    )

    total_executors = stats["total_executors"]
    active_executors = stats["active_executors"]
    coverage_pct = (active_executors / total_executors * 100) if total_executors > 0 else 0.0

    return ShiftStatsOut(
        active_shifts=stats["active_shifts"],
        active_executors=active_executors,
        coverage_pct=round(coverage_pct, 1),
        avg_efficiency=stats["avg_efficiency"],
        shifts_today=stats["shifts_today"],
        pending_transfers=stats["pending_transfers"],
    )


@router.get("/transfers", response_model=list[TransferOut])
async def list_transfers(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    rows = await service.list_transfers(db, limit=limit, offset=offset)
    out = []
    for transfer, fu, tu in rows:
        out.append(TransferOut(
            id=transfer.id,
            shift_id=transfer.shift_id,
            from_executor_name=_executor_name(fu),
            to_executor_name=_executor_name(tu) if tu else None,
            status=transfer.status,
            reason=transfer.reason,
            urgency_level=transfer.urgency_level,
            comment=transfer.comment,
            created_at=transfer.created_at,
        ))
    return out
