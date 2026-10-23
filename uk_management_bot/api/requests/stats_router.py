"""Статистика заявок дашборда: обзор, исполнители, CSV, сроки, хвост, адреса, затраты.

Тонкий HTTP-слой: парсинг периода, права (`requests.stats`), сборка DTO.
Прямого ORM здесь нет (AST-гейт `tests/api/test_stats_router_inventory.py`) —
выборки в `stats_service` и `services/request_analytics`.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.api.requests import stats_service
from uk_management_bot.database.models.user import User
from uk_management_bot.services.auto_manager.config import load_config
from uk_management_bot.services.request_analytics import csv_export
from uk_management_bot.services.request_analytics import official_report, official_xlsx
from uk_management_bot.services.request_analytics import operations
from uk_management_bot.services.request_analytics import period as P
from uk_management_bot.services.request_analytics import quality as quality_service
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


class OfficialReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lang: Literal["ru", "uz"] = Field("ru", description="Язык отчёта")
    organization: str = Field("", max_length=official_xlsx.FIELD_MAX_CHARS,
                              description="Наименование организации в шапке")
    signer: str = Field("", max_length=official_xlsx.FIELD_MAX_CHARS,
                        description="ФИО руководителя в блоке подписей")
    sheets: list[official_xlsx.SheetKey] = Field(
        default_factory=lambda: list(official_xlsx.SHEETS), min_length=1,
        max_length=len(official_xlsx.SHEETS), description="Какие листы выгрузить")
    logo: Optional[str] = Field(None, max_length=official_xlsx.LOGO_MAX_B64,
                                description="Логотип для шапки: PNG в base64")


@router.post("/stats/report")
async def export_official_report(
    body: OfficialReportIn,
    period: Period = Depends(get_period),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_STATS),
):
    """Отчёт для проверяющих органов (.xlsx): отмеченные листы из сводки, динамики, домов, реестра."""
    try:
        logo = official_xlsx.decode_logo(body.logo) if body.logo else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Некорректный логотип: {exc}") from exc
    report = await official_report.build_report(db, period.first, period.last, await _sla_hours(db))
    payload = await run_in_threadpool(
        official_xlsx.render_xlsx, report, body.lang, body.organization, body.signer,
        tuple(body.sheets), logo)
    filename = official_xlsx.report_filename(period.first, period.last, body.lang)
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


class ReportRequestRow(BaseModel):
    request_number: str
    created_at: Optional[datetime]
    status: str
    category: str
    urgency: str
    address: Optional[str]
    executor_name: Optional[str]
    completed_at: Optional[datetime]
    on_time: Optional[bool]


class ReportRequestsOut(BaseModel):
    rows: list[ReportRequestRow]
    truncated: bool


@router.get("/stats/report/requests", response_model=ReportRequestsOut)
async def official_report_requests(
    scope: Literal["all", "done"] = Query("all", description="all — поступившие, done — принятые в периоде"),
    period: Period = Depends(get_period),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_STATS),
):
    """Таблица заявок периода на вкладке «Отчёт» — до выгрузки в .xlsx."""
    rows, truncated = await official_report.list_requests(
        db, period.first, period.last, scope, await _sla_hours(db))
    return ReportRequestsOut(rows=[ReportRequestRow(**asdict(r)) for r in rows], truncated=truncated)


# ---------------------------------------------------------------------------
# Сроки и качество
# ---------------------------------------------------------------------------

class UrgencySlaOut(BaseModel):
    urgency: str
    sla_hours: int
    accepted: int
    measured: int
    median_hours: Optional[float]
    p90_hours: Optional[float]
    overdue: int


class CategoryReturnsOut(BaseModel):
    category: str
    accepted: int
    returned: int


class ReviewOut(BaseModel):
    request_number: str
    rating: int
    review: str
    executor_name: Optional[str]
    completed_at: Optional[datetime]


class QualityOut(BaseModel):
    sla_hours: dict[str, int]
    by_urgency: list[UrgencySlaOut]
    returns_by_category: list[CategoryReturnsOut]
    ratings: dict[int, int]
    recent_reviews: list[ReviewOut]


@router.get("/stats/quality", response_model=QualityOut)
async def get_quality(
    period: Period = Depends(get_period),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_STATS),
):
    data = await quality_service.quality(db, period.first, period.last, await _sla_hours(db))
    return QualityOut(**asdict(data))


# ---------------------------------------------------------------------------
# Хвост и адреса
# ---------------------------------------------------------------------------

class OpenRequestOut(BaseModel):
    request_number: str
    status: str
    category: str
    created_at: datetime
    executor_id: Optional[int]
    executor_name: Optional[str]
    age_days: float


class QueueOut(BaseModel):
    user_id: Optional[int]
    name: Optional[str]
    open: int
    oldest_age_days: float


class BacklogOut(BaseModel):
    total: int
    by_age: dict[str, int]
    queues: list[QueueOut]
    oldest: list[OpenRequestOut]


@router.get("/stats/backlog", response_model=BacklogOut)
async def get_backlog(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_STATS),
):
    """Открытые заявки сейчас: возраст, очереди исполнителей, самые старые."""
    return BacklogOut(**asdict(await operations.backlog(db)))


class AddressCountOut(BaseModel):
    id: int
    name: str
    count: int


class RepeatOut(BaseModel):
    request_number: str
    previous_number: str
    address: Optional[str]
    category: str
    days_after: float


class AddressesOut(BaseModel):
    buildings: list[AddressCountOut]
    yards: list[AddressCountOut]
    repeats: list[RepeatOut]


@router.get("/stats/addresses", response_model=AddressesOut)
async def get_addresses(
    period: Period = Depends(get_period),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_STATS),
):
    return AddressesOut(**asdict(await operations.addresses(db, period.first, period.last)))


# ---------------------------------------------------------------------------
# Каналы и затраты
# ---------------------------------------------------------------------------

class ChannelPoint(BaseModel):
    bucket: str
    counts: dict[str, int]


class ChannelsOut(BaseModel):
    granularity: Literal["day", "month", "year"]
    totals: dict[str, int]
    series: list[ChannelPoint]


@router.get("/stats/channels", response_model=ChannelsOut)
async def get_channels(
    granularity: Optional[Literal["day", "month", "year"]] = Query(None),
    period: Period = Depends(get_period),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_STATS),
):
    gran = granularity or P.auto_granularity(period.first, period.last)
    data = await operations.channels(db, period.first, period.last, gran)
    return ChannelsOut(
        granularity=gran, totals=data.totals,
        series=[ChannelPoint(bucket=b, counts=c) for b, c in data.series],
    )


class BuildingCostOut(BaseModel):
    id: int
    name: str
    amount: float


class CostsOut(BaseModel):
    total: float
    requests_with_materials: int
    accepted: int
    by_category: dict[str, float]
    by_building: list[BuildingCostOut]


@router.get("/stats/costs", response_model=CostsOut)
async def get_costs(
    period: Period = Depends(get_period),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_STATS),
):
    """Материалы по заявкам, принятым в периоде (сторно не входит)."""
    data = await operations.costs(db, period.first, period.last)
    return CostsOut(
        total=float(data.total),
        requests_with_materials=data.requests_with_materials,
        accepted=data.accepted,
        by_category={k: float(v) for k, v in data.by_category.items()},
        by_building=[BuildingCostOut(id=i, name=n, amount=float(a)) for i, n, a in data.by_building],
    )
