"""Статистика заявок дашборда: обзор периода, исполнители, CSV-выгрузки.

Тонкий HTTP-слой: парсинг периода, права (`requests.stats`), сборка DTO.
Прямого ORM здесь нет (AST-гейт `tests/api/test_stats_router_inventory.py`) —
выборки в `stats_service` и `services/request_analytics`.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.api.requests import stats_service
from uk_management_bot.database.models.user import User
from uk_management_bot.services.auto_manager.config import load_config
from uk_management_bot.services.request_analytics import csv_export
from uk_management_bot.services.request_analytics import period as P
from uk_management_bot.services.request_analytics.executors import executor_summaries

router = APIRouter()

_STATS = require_action("requests.stats")


# ---------------------------------------------------------------------------
# Период
# ---------------------------------------------------------------------------

class Period(BaseModel):
    first: date
    last: date


def get_period(
    date_from: str = Query(..., description="Первый бизнес-день периода, YYYY-MM-DD"),
    date_to: str = Query(..., description="Последний бизнес-день периода (включительно)"),
) -> Period:
    try:
        first, last = P.parse_range(date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Некорректный период: {exc}") from exc
    return Period(first=first, last=last)


async def _sla_hours(db: AsyncSession) -> dict:
    return (await load_config(db))["sla_hours"]


def _csv_response(payload: str, filename: str) -> StreamingResponse:
    return StreamingResponse(
        iter([payload]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# Обзор
# ---------------------------------------------------------------------------

class SeriesPoint(BaseModel):
    bucket: str
    created: int
    accepted: int


class KpiOut(BaseModel):
    created: int
    accepted: int
    avg_assign_hours: Optional[float]
    avg_work_hours: Optional[float]
    avg_to_accept_hours: Optional[float]
    avg_satisfaction: Optional[float]
    returned: int


class RequestStatsOut(BaseModel):
    date_from: date
    date_to: date
    granularity: Literal["day", "month", "year"]
    series: list[SeriesPoint]
    by_category: dict[str, int]
    open_by_status: dict[str, int]
    kpi: KpiOut
    previous: KpiOut


@router.get("/stats", response_model=RequestStatsOut)
async def get_request_stats(
    granularity: Optional[Literal["day", "month", "year"]] = Query(
        None, description="Срез оси; без параметра — авто по длине периода"),
    period: Period = Depends(get_period),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_STATS),
):
    gran = granularity or P.auto_granularity(period.first, period.last)
    data = await stats_service.overview(db, period.first, period.last, gran)
    return RequestStatsOut(
        date_from=period.first,
        date_to=period.last,
        granularity=gran,
        series=[SeriesPoint(bucket=b, created=c, accepted=a) for b, c, a in data.series],
        by_category=data.by_category,
        open_by_status=data.open_by_status,
        kpi=KpiOut(**asdict(data.kpi)),
        previous=KpiOut(**asdict(data.previous)),
    )


# ---------------------------------------------------------------------------
# Исполнители
# ---------------------------------------------------------------------------

class ExecutorRow(BaseModel):
    user_id: Optional[int]
    name: Optional[str]
    executed: int
    accepted: int
    returned: int
    overdue: int
    avg_work_hours: Optional[float]
    avg_to_accept_hours: Optional[float]
    avg_rating: Optional[float]
    ratings_count: int
    in_work_now: int
    materials_cost: float


@router.get("/stats/executors", response_model=list[ExecutorRow])
async def get_executor_stats(
    period: Period = Depends(get_period),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_STATS),
):
    rows = await executor_summaries(db, period.first, period.last, await _sla_hours(db))
    return [ExecutorRow(**{**asdict(r), "materials_cost": float(r.materials_cost)}) for r in rows]


@router.get("/stats/export")
async def export_completed(
    executor_id: Optional[int] = Query(None, description="Только этот исполнитель"),
    period: Period = Depends(get_period),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_STATS),
):
    """CSV принятых в периоде заявок (по строке на заявку)."""
    payload, _count = await csv_export.build_completed_csv(
        db, period.first, period.last, await _sla_hours(db), executor_id=executor_id)
    suffix = f"executor{executor_id}" if executor_id is not None else ""
    return _csv_response(payload, csv_export.export_filename(
        "completed_requests", period.first, period.last, suffix))


@router.get("/stats/export/executors")
async def export_executors(
    period: Period = Depends(get_period),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_STATS),
):
    """CSV сводки по исполнителям (по строке на человека)."""
    rows = await executor_summaries(db, period.first, period.last, await _sla_hours(db))
    return _csv_response(csv_export.executors_csv(rows), csv_export.export_filename(
        "executors_summary", period.first, period.last))
