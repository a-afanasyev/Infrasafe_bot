"""Отчёт для проверяющих органов (хокимият, налоговая и т. п.): данные периода.

Правила зачёта — те же, что у аналитики дашборда (`docs/tech/ANALYTICS.md`):
* «поступило» — `created_at` в периоде;
* «выполнено» — статус «Принято» и `completed_at` в периоде (`load_accepted`);
* «в срок» — создание → сдача работы не дольше `sla_hours[urgency]`;
  у заявок без отметок срок не измерим — ни в срок, ни с нарушением.
Состояние поступивших («выполнено / в работе / отменено») — снимок на момент
формирования: истории статусов нет, на конец периода честно не восстановить.

Рендер в .xlsx — `official_xlsx.py`; здесь только выборки и агрегаты.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, select
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
    URGENCY_RU_TO_KEY,
)

from . import period as P
from .executors import AcceptedRequest, load_accepted, person_name

#: Реестр — как лимит CSV-выгрузки; итоги считаются по всем заявкам.
REGISTER_LIMIT = 10_000
URGENCY_ORDER = ("critical", "high", "medium", "low")


@dataclass(frozen=True)
class ListRow:
    """Строка таблицы «Отчёт» в дашборде (до выгрузки)."""
    request_number: str
    created_at: Optional[datetime]
    status: str
    category: str
    urgency: str
    address: Optional[str]
    executor_name: Optional[str]
    completed_at: Optional[datetime]
    #: Только у принятых: уложились ли в норматив (как «Срок соблюдён» в реестре).
    on_time: Optional[bool]


def _on_time(status: str, urgency: str, hours: Optional[float], sla_hours: dict) -> Optional[bool]:
    limit = sla_hours.get(urgency)
    if status != REQUEST_STATUS_APPROVED or hours is None or limit is None:
        return None
    return hours <= limit


async def list_requests(
    db: AsyncSession, first: date, last: date, scope: str, sla_hours: dict,
) -> tuple[list[ListRow], bool]:
    """`all` — поступившие в периоде (по `created_at`), `done` — принятые в
    периоде (ровно строки листа «Реестр»). Не больше `REGISTER_LIMIT` строк."""
    if scope == "done":
        accepted = sorted(await load_accepted(db, first, last),
                          key=lambda r: (r.completed_at, r.request_number))
        rows = [
            ListRow(r.request_number, r.created_at, REQUEST_STATUS_APPROVED, resolve_category_key(r.category),
                    r.urgency, r.address, r.executor_name, r.completed_at,
                    _on_time(REQUEST_STATUS_APPROVED, r.urgency, r.resolution_hours, sla_hours))
            for r in accepted
        ]
        return rows[:REGISTER_LIMIT], len(rows) > REGISTER_LIMIT

    start, end = business_days_window(first, last)
    executor = aliased(User)
    result = await db.execute(
        select(Request.request_number, Request.created_at, Request.status, Request.category,
               Request.urgency, Request.address, executor.first_name, executor.last_name,
               Request.executed_at, Request.completed_at)
        .outerjoin(executor, Request.executor_id == executor.id)
        .where(Request.created_at >= start, Request.created_at < end)
        .order_by(Request.created_at, Request.request_number)
        .limit(REGISTER_LIMIT + 1)
    )
    rows = []
    for number, created, status, category, urgency, address, first_name, last_name, executed, completed in result.all():
        urgency_key = URGENCY_RU_TO_KEY.get(urgency, urgency)
        hours = P.hours_between(created, executed or completed)
        rows.append(ListRow(number, created, status, resolve_category_key(category), urgency_key, address,
                            person_name(first_name, last_name), completed,
                            _on_time(status, urgency_key, hours, sla_hours)))
    return rows[:REGISTER_LIMIT], len(rows) > REGISTER_LIMIT


@dataclass
class Tally:
    """Счётчики одной строки разбивки (вид работ, дом, срочность)."""
    created: int = 0
    accepted: int = 0
    on_time: int = 0
    overdue: int = 0
    hours_sum: float = 0.0
    hours_count: int = 0

    def add_accepted(self, row: AcceptedRequest, sla_hours: dict) -> None:
        self.accepted += 1
        overdue = row.is_overdue(sla_hours)
        if overdue is True:
            self.overdue += 1
        elif overdue is False:
            self.on_time += 1
        if row.resolution_hours is not None:
            self.hours_sum += row.resolution_hours
            self.hours_count += 1

    @property
    def on_time_share(self) -> Optional[float]:
        measured = self.on_time + self.overdue
        return self.on_time / measured if measured else None

    @property
    def avg_hours(self) -> Optional[float]:
        return round(self.hours_sum / self.hours_count, 1) if self.hours_count else None


@dataclass(frozen=True)
class BuildingRow:
    address: str
    yard: Optional[str]
    tally: Tally


@dataclass(frozen=True)
class OfficialReport:
    first: date
    last: date
    generated_at: datetime
    granularity: P.Granularity
    sla_hours: dict
    total: Tally
    #: Поступившие в периоде по текущему состоянию.
    created_done: int
    created_in_work: int
    created_cancelled: int
    returned: int
    avg_rating: Optional[float]
    ratings_count: int
    by_category: list[tuple[str, Tally]]
    by_urgency: list[tuple[str, Tally]]
    #: Последняя строка с `address=""` — заявки без привязки к дому.
    by_building: list[BuildingRow]
    series: list[tuple[str, int, int]]  # (бакет, поступило, выполнено)
    register: list[AcceptedRequest]
    register_truncated: bool
    descriptions: dict[str, str]


async def _created_rows(db: AsyncSession, first: date, last: date) -> list[tuple]:
    start, end = business_days_window(first, last)
    building_id = func.coalesce(Request.building_id, Apartment.building_id)
    rows = await db.execute(
        select(Request.created_at, Request.category, Request.status, building_id)
        .outerjoin(Apartment, Request.apartment_id == Apartment.id)
        .where(Request.created_at >= start, Request.created_at < end)
    )
    return rows.all()


async def _building_names(db: AsyncSession, ids: set[int]) -> dict[int, tuple[str, Optional[str]]]:
    if not ids:
        return {}
    rows = await db.execute(
        select(Building.id, Building.address, Yard.name)
        .outerjoin(Yard, Building.yard_id == Yard.id)
        .where(Building.id.in_(sorted(ids)))
    )
    return {bid: (address, yard) for bid, address, yard in rows.all()}


async def _descriptions(db: AsyncSession, numbers: list[str]) -> dict[str, str]:
    if not numbers:
        return {}
    rows = await db.execute(
        select(Request.request_number, Request.description)
        .where(Request.request_number.in_(numbers))
    )
    return {n: d or "" for n, d in rows.all()}


async def build_report(
    db: AsyncSession, first: date, last: date, sla_hours: dict,
    now: Optional[datetime] = None,
) -> OfficialReport:
    created = await _created_rows(db, first, last)
    accepted = await load_accepted(db, first, last)
    granularity: P.Granularity = "day" if (last - first).days < 31 else "month"

    total = Tally(created=len(created))
    categories: dict[str, Tally] = {}
    urgencies: dict[str, Tally] = {u: Tally() for u in URGENCY_ORDER}
    buildings: dict[Optional[int], Tally] = {}
    done = cancelled = 0
    for created_at, category, status, building_id in created:
        categories.setdefault(resolve_category_key(category), Tally()).created += 1
        buildings.setdefault(building_id, Tally()).created += 1
        if status == REQUEST_STATUS_APPROVED:
            done += 1
        elif status == REQUEST_STATUS_CANCELLED:
            cancelled += 1

    for row in accepted:
        total.add_accepted(row, sla_hours)
        categories.setdefault(resolve_category_key(row.category), Tally()).add_accepted(row, sla_hours)
        urgencies.setdefault(row.urgency, Tally()).add_accepted(row, sla_hours)
        buildings.setdefault(row.building_id, Tally()).add_accepted(row, sla_hours)

    names = await _building_names(db, {b for b in buildings if b is not None})
    by_building = sorted(
        (BuildingRow(address=names.get(bid, (f"#{bid}", None))[0],
                     yard=names.get(bid, ("", None))[1], tally=t)
         for bid, t in buildings.items() if bid is not None),
        key=lambda b: (b.yard or "", b.address),
    )
    if None in buildings:
        by_building.append(BuildingRow(address="", yard=None, tally=buildings[None]))

    series = {key: [0, 0] for key in P.axis(first, last, granularity)}
    for created_at, *_ in created:
        if created_at is not None:
            series[P.bucket_key(business_date_of(created_at), granularity)][0] += 1
    for row in accepted:
        series[P.bucket_key(business_date_of(row.completed_at), granularity)][1] += 1

    ratings = [r.rating for r in accepted if r.rating is not None]
    register = sorted(accepted, key=lambda r: (r.completed_at, r.request_number))[:REGISTER_LIMIT]
    return OfficialReport(
        first=first, last=last,
        generated_at=now or datetime.now(timezone.utc),
        granularity=granularity,
        sla_hours=sla_hours,
        total=total,
        created_done=done,
        created_in_work=len(created) - done - cancelled,
        created_cancelled=cancelled,
        returned=sum(1 for r in accepted if r.returned_by),
        avg_rating=P.mean(float(x) for x in ratings),
        ratings_count=len(ratings),
        by_category=sorted(categories.items(), key=lambda kv: (-kv[1].accepted, -kv[1].created, kv[0])),
        by_urgency=list(urgencies.items()),
        by_building=by_building,
        series=[(k, c, a) for k, (c, a) in series.items()],
        register=register,
        register_truncated=len(accepted) > REGISTER_LIMIT,
        descriptions=await _descriptions(db, [r.request_number for r in register]),
    )
