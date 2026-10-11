"""Хвост, адреса, каналы и затраты (фазы 4–5 плана аналитики).

* хвост — снимок открытых заявок «сейчас», без периода;
* адреса — заявки, СОЗДАННЫЕ в периоде, по домам/дворам + повторные;
* каналы — созданные в периоде по `source`;
* затраты — материалы по заявкам, ПРИНЯТЫМ в периоде (как в сводке исполнителей).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.utils.business_time import business_date_of, business_days_window
from uk_management_bot.utils.categories import resolve_category_key
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_APPROVED,
    REQUEST_STATUS_CANCELLED,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_EXECUTED,
    REQUEST_STATUS_RETURNED,
)
from uk_management_bot.utils.workflow_predicates import status_in_clause

from . import period as P
from .executors import load_accepted, person_name

#: Открытая заявка — работа ещё не сдана (как «Открытые по статусам» обзора).
NOT_OPEN_STATUSES = (
    REQUEST_STATUS_EXECUTED, REQUEST_STATUS_COMPLETED, REQUEST_STATUS_RETURNED,
    REQUEST_STATUS_APPROVED, REQUEST_STATUS_CANCELLED,
)
#: Возраст открытых заявок: (ключ, верхняя граница в днях, None — без границы).
AGE_BUCKETS = (("lt1", 1), ("d1_3", 3), ("d3_7", 7), ("d7_30", 30), ("gt30", None))
OLDEST_LIMIT = 20
TOP_ADDRESSES = 10
REPEAT_WINDOW_DAYS = 30


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)


def age_bucket(age_days: float) -> str:
    for key, upper in AGE_BUCKETS:
        if upper is None or age_days < upper:
            return key
    return AGE_BUCKETS[-1][0]


# ───────────────────────────── хвост ─────────────────────────────

@dataclass(frozen=True)
class OpenRequest:
    request_number: str
    status: str
    category: str
    created_at: datetime
    executor_id: Optional[int]
    executor_name: Optional[str]
    age_days: float


@dataclass(frozen=True)
class QueueRow:
    user_id: Optional[int]
    name: Optional[str]
    open: int
    oldest_age_days: float


@dataclass(frozen=True)
class Backlog:
    total: int
    by_age: dict[str, int]
    queues: list[QueueRow]
    oldest: list[OpenRequest]


async def backlog(db: AsyncSession, now: Optional[datetime] = None) -> Backlog:
    now = now or datetime.now(timezone.utc)
    executor = aliased(User)
    rows = (await db.execute(
        select(Request.request_number, Request.status, Request.category, Request.created_at,
               Request.executor_id, executor.first_name, executor.last_name)
        .outerjoin(executor, Request.executor_id == executor.id)
        .where(not_(status_in_clause(NOT_OPEN_STATUSES)), Request.created_at.isnot(None))
    )).all()
    items = [
        OpenRequest(
            request_number=r[0], status=r[1], category=r[2], created_at=r[3],
            executor_id=r[4], executor_name=person_name(r[5], r[6]),
            age_days=round(max(0.0, (now - _aware(r[3])).total_seconds()) / 86400, 1),
        )
        for r in rows
    ]
    by_age = {key: 0 for key, _ in AGE_BUCKETS}
    for item in items:
        by_age[age_bucket(item.age_days)] += 1

    queues: dict[Optional[int], list[OpenRequest]] = {}
    for item in items:
        queues.setdefault(item.executor_id, []).append(item)
    queue_rows = sorted(
        (QueueRow(user_id=uid, name=group[0].executor_name, open=len(group),
                  oldest_age_days=max(i.age_days for i in group))
         for uid, group in queues.items()),
        key=lambda q: (-q.open, -q.oldest_age_days),
    )
    oldest = sorted(items, key=lambda i: -i.age_days)[:OLDEST_LIMIT]
    return Backlog(total=len(items), by_age=by_age, queues=queue_rows, oldest=oldest)


# ───────────────────────────── адреса ─────────────────────────────

@dataclass(frozen=True)
class AddressCount:
    id: int
    name: str
    count: int


@dataclass(frozen=True)
class RepeatRequest:
    request_number: str
    previous_number: str
    address: Optional[str]
    category: str
    days_after: float


@dataclass(frozen=True)
class Addresses:
    buildings: list[AddressCount]
    yards: list[AddressCount]
    repeats: list[RepeatRequest]


def _top(counts: dict[int, int], names: dict[int, str]) -> list[AddressCount]:
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], names.get(kv[0], "")))
    return [AddressCount(id=k, name=names.get(k, f"#{k}"), count=n) for k, n in ranked[:TOP_ADDRESSES]]


async def _repeats(db: AsyncSession, start: datetime, end: datetime) -> list[RepeatRequest]:
    """Заявки периода, поданные по той же квартире и категории в течение
    `REPEAT_WINDOW_DAYS` после приёмки предыдущей."""
    window = timedelta(days=REPEAT_WINDOW_DAYS)
    later = (await db.execute(
        select(Request.request_number, Request.apartment_id, Request.category,
               Request.created_at, Request.address)
        .where(Request.created_at >= start, Request.created_at < end,
               Request.apartment_id.isnot(None))
    )).all()
    if not later:
        return []
    earlier = (await db.execute(
        select(Request.request_number, Request.apartment_id, Request.category,
               Request.completed_at)
        .where(status_in_clause([REQUEST_STATUS_APPROVED]),
               Request.apartment_id.in_(sorted({r[1] for r in later})),
               Request.completed_at >= start - window, Request.completed_at < end)
    )).all()
    accepted: dict[tuple, list[tuple[str, datetime]]] = {}
    for number, apt, category, completed in earlier:
        accepted.setdefault((apt, resolve_category_key(category)), []).append(
            (number, _aware(completed)))
    repeats = []
    for number, apt, category, created, address in later:
        created = _aware(created)
        previous = [
            (prev, done) for prev, done in accepted.get((apt, resolve_category_key(category)), [])
            if prev != number and done < created <= done + window
        ]
        if previous:
            prev_number, done = max(previous, key=lambda p: p[1])
            repeats.append(RepeatRequest(
                request_number=number, previous_number=prev_number, address=address,
                category=resolve_category_key(category),
                days_after=round((created - done).total_seconds() / 86400, 1),
            ))
    return sorted(repeats, key=lambda r: r.request_number)


async def addresses(db: AsyncSession, first: date, last: date) -> Addresses:
    start, end = business_days_window(first, last)
    building_id = func.coalesce(Request.building_id, Apartment.building_id)
    rows = (await db.execute(
        select(building_id, func.coalesce(Request.yard_id, Building.yard_id))
        .outerjoin(Apartment, Request.apartment_id == Apartment.id)
        .outerjoin(Building, Building.id == building_id)
        .where(Request.created_at >= start, Request.created_at < end)
    )).all()
    by_building: dict[int, int] = {}
    by_yard: dict[int, int] = {}
    for bid, yid in rows:
        if bid is not None:
            by_building[bid] = by_building.get(bid, 0) + 1
        if yid is not None:
            by_yard[yid] = by_yard.get(yid, 0) + 1
    building_names = dict((await db.execute(
        select(Building.id, Building.address).where(Building.id.in_(list(by_building) or [0]))
    )).all())
    yard_names = dict((await db.execute(
        select(Yard.id, Yard.name).where(Yard.id.in_(list(by_yard) or [0]))
    )).all())
    return Addresses(
        buildings=_top(by_building, building_names),
        yards=_top(by_yard, yard_names),
        repeats=await _repeats(db, start, end),
    )


# ───────────────────────────── каналы и затраты ─────────────────────────────

@dataclass(frozen=True)
class Channels:
    totals: dict[str, int]
    series: list[tuple[str, dict[str, int]]]


async def channels(
    db: AsyncSession, first: date, last: date, granularity: P.Granularity,
) -> Channels:
    start, end = business_days_window(first, last)
    rows = (await db.execute(
        select(Request.created_at, Request.source)
        .where(Request.created_at >= start, Request.created_at < end)
    )).all()
    totals: dict[str, int] = {}
    buckets: dict[str, dict[str, int]] = {key: {} for key in P.axis(first, last, granularity)}
    for created, source in rows:
        key = source or "unknown"
        totals[key] = totals.get(key, 0) + 1
        bucket = buckets.setdefault(P.bucket_key(business_date_of(created), granularity), {})
        bucket[key] = bucket.get(key, 0) + 1
    return Channels(totals=totals, series=list(buckets.items()))


@dataclass(frozen=True)
class Costs:
    total: Decimal
    requests_with_materials: int
    accepted: int
    by_category: dict[str, Decimal]
    by_building: list[tuple[int, str, Decimal]]


async def costs(db: AsyncSession, first: date, last: date) -> Costs:
    from uk_management_bot.services.material_service import get_requests_material_costs

    rows = await load_accepted(db, first, last)
    per_request = await get_requests_material_costs(db, [r.request_number for r in rows])
    by_category: dict[str, Decimal] = {}
    by_building: dict[int, Decimal] = {}
    for r in rows:
        cost = per_request.get(r.request_number)
        if cost is None:
            continue
        key = resolve_category_key(r.category)
        by_category[key] = by_category.get(key, Decimal("0")) + cost
        if r.building_id is not None:
            by_building[r.building_id] = by_building.get(r.building_id, Decimal("0")) + cost
    names = dict((await db.execute(
        select(Building.id, Building.address).where(Building.id.in_(list(by_building) or [0]))
    )).all())
    ranked = sorted(by_building.items(), key=lambda kv: -kv[1])[:TOP_ADDRESSES]
    return Costs(
        total=sum(per_request.values(), Decimal("0")),
        requests_with_materials=len(per_request),
        accepted=len(rows),
        by_category=dict(sorted(by_category.items(), key=lambda kv: -kv[1])),
        by_building=[(bid, names.get(bid, f"#{bid}"), amount) for bid, amount in ranked],
    )
