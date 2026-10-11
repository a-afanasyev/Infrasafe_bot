"""Async data-access слой статистики заявок дашборда (ARC-06).

Роутер `api/requests/stats_router.py` — тонкий HTTP-слой без ORM (AST-гейт
`tests/api/test_stats_router_inventory.py`). Здесь — выборки обзора за
календарный период; исполнители, выгрузки, сроки и прочие срезы живут в
общем для API и бота пакете `services/request_analytics`.

Период — бизнес-даты включительно → полуоткрытое UTC-окно
(`business_days_window`). Бакеты дня/месяца/года считаются в Python по
бизнес-дате (`func.date` резал сутки по зоне сессии БД — ARCH-135); объёмы
пилотные, выборка — одна колонка за период.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.request import Request
from uk_management_bot.services.request_analytics import period as P
from uk_management_bot.services.request_analytics.executors import AcceptedRequest, load_accepted
from uk_management_bot.utils.business_time import business_days_window
from uk_management_bot.utils.categories import resolve_category_key
from uk_management_bot.utils.workflow_predicates import status_in_clause
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_APPROVED,
    REQUEST_STATUS_CANCELLED,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_EXECUTED,
    REQUEST_STATUS_RETURNED,
)

#: Не «открытые»: работа сдана (ждёт проверки/приёмки), принята или отменена.
NOT_OPEN_STATUSES = [
    REQUEST_STATUS_EXECUTED, REQUEST_STATUS_COMPLETED, REQUEST_STATUS_RETURNED,
    REQUEST_STATUS_APPROVED, REQUEST_STATUS_CANCELLED,
]


@dataclass(frozen=True)
class Kpi:
    created: int
    accepted: int
    avg_assign_hours: Optional[float]
    avg_work_hours: Optional[float]
    avg_to_accept_hours: Optional[float]
    avg_satisfaction: Optional[float]
    returned: int


@dataclass(frozen=True)
class Overview:
    series: list[tuple[str, int, int]]  # (bucket, created, accepted)
    by_category: dict[str, int]
    open_by_status: dict[str, int]
    kpi: Kpi
    previous: Kpi


async def _created(db: AsyncSession, first: date, last: date) -> list[tuple]:
    start, end = business_days_window(first, last)
    rows = await db.execute(
        select(Request.created_at, Request.category)
        .where(Request.created_at >= start, Request.created_at < end)
    )
    return rows.all()


def _kpi(created: int, accepted: list[AcceptedRequest]) -> Kpi:
    return Kpi(
        created=created,
        accepted=len(accepted),
        avg_assign_hours=P.mean(P.hours_between(r.created_at, r.assigned_at) for r in accepted),
        avg_work_hours=P.mean(r.work_hours for r in accepted),
        avg_to_accept_hours=P.mean(r.to_accept_hours for r in accepted),
        avg_satisfaction=P.mean(float(r.rating) for r in accepted if r.rating is not None),
        returned=sum(1 for r in accepted if r.returned_by),
    )


async def open_by_status(db: AsyncSession) -> dict[str, int]:
    """Открытые заявки сейчас по статусам — снимок, без периода."""
    rows = await db.execute(
        select(Request.status, func.count())
        .where(not_(status_in_clause(NOT_OPEN_STATUSES)))
        .group_by(Request.status)
    )
    return {status: n for status, n in rows.all() if status}


async def overview(
    db: AsyncSession, first: date, last: date, granularity: P.Granularity,
) -> Overview:
    created = await _created(db, first, last)
    accepted = await load_accepted(db, first, last)
    created_buckets = P.count_by_bucket((ts for ts, _ in created), granularity)
    accepted_buckets = P.count_by_bucket((r.completed_at for r in accepted), granularity)
    series = [
        (key, created_buckets.get(key, 0), accepted_buckets.get(key, 0))
        for key in P.axis(first, last, granularity)
    ]

    # FS-04: legacy RU-лейблы схлопываются в канон-ключ — иначе дольки двоятся.
    by_category: dict[str, int] = {}
    for _, raw in created:
        if raw:
            key = resolve_category_key(raw)
            by_category[key] = by_category.get(key, 0) + 1

    prev_first, prev_last = P.previous_range(first, last)
    prev_created = await _created(db, prev_first, prev_last)
    prev_accepted = await load_accepted(db, prev_first, prev_last)
    return Overview(
        series=series,
        by_category=by_category,
        open_by_status=await open_by_status(db),
        kpi=_kpi(len(created), accepted),
        previous=_kpi(len(prev_created), prev_accepted),
    )
