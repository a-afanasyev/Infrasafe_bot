"""Аналитика по исполнителям: принятые заявки периода и сводка «сколько и как».

Правила зачёта (решения владельца 2026-10-12):
* «принято» — статус «Принято» и `completed_at` в периоде; заявка засчитана
  ТЕКУЩЕМУ `executor_id` (переназначение до приёмки уводит её новому);
* «выполнено» — `executed_at` в периоде (сдача работы, даже если ещё не приняли);
* возврат — `returned_at` (житель) или `manager_return_reason` (менеджер).
  Флаг `is_returned` для отчёта не годится: планировщик сбрасывает его при
  повторном выполнении и приёмке, у принятых заявок он всегда False;
* норматив — часы от создания до сдачи работы (`executed_at`; у заявок до
  появления поля — до приёмки) против `sla_hours[urgency]`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.rating import Rating
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.business_time import business_days_window
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_APPROVED,
    REQUEST_STATUS_CANCELLED,
    REQUEST_STATUS_CLARIFICATION,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_PURCHASE,
    URGENCY_RU_TO_KEY,
)
from uk_management_bot.utils.workflow_predicates import status_in_clause

from .period import hours_between, mean

#: «В работе сейчас» у исполнителя — заявка на нём и ещё не сдана.
IN_WORK_STATUSES = (
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_PURCHASE,
    REQUEST_STATUS_CLARIFICATION,
)

RETURNED_BY_RESIDENT = "resident"
RETURNED_BY_MANAGER = "manager"


def person_name(first: Optional[str], last: Optional[str]) -> Optional[str]:
    return f"{first or ''} {last or ''}".strip() or None


@dataclass(frozen=True)
class AcceptedRequest:
    request_number: str
    executor_id: Optional[int]
    executor_name: Optional[str]
    category: str
    urgency: str
    source: Optional[str]
    address: Optional[str]
    created_at: Optional[datetime]
    assigned_at: Optional[datetime]
    executed_at: Optional[datetime]
    completed_at: Optional[datetime]
    returned_at: Optional[datetime]
    manager_return_reason: Optional[str]
    return_reason: Optional[str]
    completion_report: Optional[str]
    has_photos: bool
    rating: Optional[int]
    review: Optional[str]
    apartment_id: Optional[int]
    building_id: Optional[int]
    yard_id: Optional[int]

    @property
    def work_hours(self) -> Optional[float]:
        return hours_between(self.assigned_at, self.executed_at)

    @property
    def to_accept_hours(self) -> Optional[float]:
        return hours_between(self.created_at, self.completed_at)

    @property
    def resolution_hours(self) -> Optional[float]:
        """Создание → сдача работы (база норматива); до executed_at — до приёмки."""
        return hours_between(self.created_at, self.executed_at or self.completed_at)

    @property
    def returned_by(self) -> Optional[str]:
        if self.returned_at is not None:
            return RETURNED_BY_RESIDENT
        if self.manager_return_reason:
            return RETURNED_BY_MANAGER
        return None

    def sla_limit(self, sla_hours: dict) -> Optional[int]:
        return sla_hours.get(self.urgency)

    def is_overdue(self, sla_hours: dict) -> Optional[bool]:
        hours, limit = self.resolution_hours, self.sla_limit(sla_hours)
        if hours is None or limit is None:
            return None
        return hours > limit


async def load_accepted(
    db: AsyncSession, first: date, last: date, *, executor_id: Optional[int] = None,
    limit: Optional[int] = None,
) -> list[AcceptedRequest]:
    """Принятые в периоде заявки; порядок — исполнитель, затем момент приёмки."""
    start, end = business_days_window(first, last)
    executor = aliased(User)
    query = (
        select(
            Request.request_number, Request.executor_id, executor.first_name,
            executor.last_name, Request.category, Request.urgency, Request.source,
            Request.address, Request.created_at, Request.assigned_at,
            Request.executed_at, Request.completed_at, Request.returned_at,
            Request.manager_return_reason, Request.return_reason,
            Request.completion_report, Request.completion_media, Rating.rating,
            Rating.review, Request.apartment_id,
            func.coalesce(Request.building_id, Apartment.building_id), Request.yard_id,
        )
        .outerjoin(executor, Request.executor_id == executor.id)
        .outerjoin(Rating, Rating.request_number == Request.request_number)
        .outerjoin(Apartment, Request.apartment_id == Apartment.id)
        .where(
            status_in_clause([REQUEST_STATUS_APPROVED]),
            Request.completed_at >= start,
            Request.completed_at < end,
        )
        .order_by(executor.last_name, executor.first_name, Request.executor_id,
                  Request.completed_at, Request.request_number)
    )
    if executor_id is not None:
        query = query.where(Request.executor_id == executor_id)
    if limit is not None:
        query = query.limit(limit)
    rows = (await db.execute(query)).all()
    return [
        AcceptedRequest(
            request_number=r[0], executor_id=r[1], executor_name=person_name(r[2], r[3]),
            category=r[4], urgency=URGENCY_RU_TO_KEY.get(r[5], r[5]), source=r[6], address=r[7], created_at=r[8],
            assigned_at=r[9], executed_at=r[10], completed_at=r[11], returned_at=r[12],
            manager_return_reason=r[13], return_reason=r[14], completion_report=r[15],
            has_photos=bool(r[16]), rating=r[17], review=r[18], apartment_id=r[19],
            building_id=r[20], yard_id=r[21],
        )
        for r in rows
    ]


async def executed_counts(db: AsyncSession, first: date, last: date) -> dict[Optional[int], int]:
    """{executor_id: сколько работ сдано в периоде} (по `executed_at`)."""
    start, end = business_days_window(first, last)
    rows = await db.execute(
        select(Request.executor_id, func.count())
        .where(
            Request.executed_at >= start,
            Request.executed_at < end,
            not_(status_in_clause([REQUEST_STATUS_CANCELLED])),
        )
        .group_by(Request.executor_id)
    )
    return {uid: n for uid, n in rows.all()}


async def in_work_counts(db: AsyncSession) -> dict[int, int]:
    """{executor_id: сколько заявок на нём сейчас в работе} — без периода."""
    rows = await db.execute(
        select(Request.executor_id, func.count())
        .where(status_in_clause(IN_WORK_STATUSES), Request.executor_id.isnot(None))
        .group_by(Request.executor_id)
    )
    return {uid: n for uid, n in rows.all()}


async def load_names(db: AsyncSession, ids) -> dict[int, Optional[str]]:
    ids = [i for i in ids if i is not None]
    if not ids:
        return {}
    rows = await db.execute(
        select(User.id, User.first_name, User.last_name).where(User.id.in_(ids))
    )
    return {uid: person_name(first, last) for uid, first, last in rows.all()}


@dataclass(frozen=True)
class ExecutorSummary:
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
    materials_cost: Decimal


def summarize(
    accepted: list[AcceptedRequest], executed: dict, in_work: dict, names: dict,
    costs: dict[str, Decimal], sla_hours: dict,
) -> list[ExecutorSummary]:
    """Строка на каждого, кто в периоде сдал/получил приёмку или держит работу сейчас."""
    by_executor: dict[Optional[int], list[AcceptedRequest]] = {}
    for row in accepted:
        by_executor.setdefault(row.executor_id, []).append(row)
    ids = set(by_executor) | set(executed) | set(in_work)
    summaries = []
    for uid in ids:
        rows = by_executor.get(uid, [])
        ratings = [r.rating for r in rows if r.rating is not None]
        summaries.append(ExecutorSummary(
            user_id=uid,
            name=names.get(uid) or next((r.executor_name for r in rows if r.executor_name), None),
            executed=executed.get(uid, 0),
            accepted=len(rows),
            returned=sum(1 for r in rows if r.returned_by),
            overdue=sum(1 for r in rows if r.is_overdue(sla_hours)),
            avg_work_hours=mean(r.work_hours for r in rows),
            avg_to_accept_hours=mean(r.to_accept_hours for r in rows),
            avg_rating=mean(float(x) for x in ratings),
            ratings_count=len(ratings),
            in_work_now=in_work.get(uid, 0) if uid is not None else 0,
            materials_cost=sum((costs.get(r.request_number, Decimal("0")) for r in rows),
                               Decimal("0")),
        ))
    return sorted(summaries, key=lambda s: (-s.accepted, -s.executed, s.name or ""))


async def executor_summaries(
    db: AsyncSession, first: date, last: date, sla_hours: dict,
) -> list[ExecutorSummary]:
    from uk_management_bot.services.material_service import get_requests_material_costs

    accepted = await load_accepted(db, first, last)
    executed = await executed_counts(db, first, last)
    in_work = await in_work_counts(db)
    names = await load_names(db, set(executed) | set(in_work) | {r.executor_id for r in accepted})
    costs = await get_requests_material_costs(db, [r.request_number for r in accepted])
    return summarize(accepted, executed, in_work, names, costs, sla_hours)
