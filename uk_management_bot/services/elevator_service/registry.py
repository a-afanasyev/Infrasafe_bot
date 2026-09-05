"""Реестр лифтов для дашборда: фильтры, пагинация, сводка по дворам.

Масштаб — сотни лифтов: список грузит дом одним ``selectinload``; сводка
считается в Python по одной плоской выборке колонок + одному запросу
просроченных ТО + одному счётчику заявок (без N+1).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from types import MappingProxyType
from typing import Any

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.elevator import (
    Elevator,
    ElevatorMaintenanceOccurrence,
)
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.utils.datetime_utils import as_utc
from uk_management_bot.utils.request_workflow import TERMINAL_STATUSES

from ._core import ELEVATOR_CATEGORY, ElevatorValidationError
from ._shared import now_or_utc, today_of
from .reminder_rules import DEFAULT_ELEVATORS_CONFIG, DOWNTIME_STATUSES, downtime_threshold_reached
from .validation import validate_status

# Флаги-фильтры реестра
FLAG_NO_CONTRACT = "no_contract"
FLAG_CERT_EXPIRED = "cert_expired"
FLAG_MAINTENANCE_OVERDUE = "maintenance_overdue"
REGISTRY_FLAGS: frozenset[str] = frozenset({FLAG_NO_CONTRACT, FLAG_CERT_EXPIRED, FLAG_MAINTENANCE_OVERDUE})
# Просрочка ТО — с 8-го дня после due_on (паритет с calendar_rules.is_overdue)
MAINTENANCE_OVERDUE_GRACE_DAYS = 7
MAX_PAGE = 500


# ---------------------------------------------------------------------------
# DTO сводки
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ElevatorCounters:
    """Счётчики по группе активных лифтов."""

    total: int
    by_status: Mapping[str, int]
    no_contract: int
    cert_expired: int
    maintenance_overdue: int
    downtime_over_threshold: int


@dataclass(frozen=True)
class YardElevatorSummary:
    yard_id: int
    yard_name: str
    counters: ElevatorCounters


@dataclass(frozen=True)
class ElevatorSummary:
    """Сводка дашборда: итого, по дворам, лифтовые заявки без лифта."""

    today: date
    totals: ElevatorCounters
    yards: tuple[YardElevatorSummary, ...]
    requests_without_elevator: int


# ---------------------------------------------------------------------------
# Фильтры реестра
# ---------------------------------------------------------------------------

def _no_contract(today: date):
    return or_(Elevator.contract_until.is_(None), Elevator.contract_until < today)


def _cert_expired(today: date):
    return or_(Elevator.cert_valid_until.is_(None), Elevator.cert_valid_until < today)


def _overdue_cutoff(today: date) -> date:
    return today - timedelta(days=MAINTENANCE_OVERDUE_GRACE_DAYS)


def _maintenance_overdue_exists(today: date):
    return exists(
        select(ElevatorMaintenanceOccurrence.id).where(
            ElevatorMaintenanceOccurrence.elevator_id == Elevator.id,
            ElevatorMaintenanceOccurrence.kind == "maintenance",
            ElevatorMaintenanceOccurrence.state == "planned",
            ElevatorMaintenanceOccurrence.due_on < _overdue_cutoff(today),
        )
    )


def _validate_flags(flags: set[str] | None) -> frozenset[str]:
    unknown = sorted(set(flags or ()) - REGISTRY_FLAGS)
    if unknown:
        raise ElevatorValidationError(f"неизвестные флаги реестра: {', '.join(unknown)}")
    return frozenset(flags or ())


def _apply_registry_filters(
    stmt: Select,
    *,
    yard_id: int | None,
    building_id: int | None,
    status: str | None,
    only_commissioned: bool | None,
    include_archived: bool,
    flags: frozenset[str],
    today: date,
) -> Select:
    if not include_archived:
        stmt = stmt.where(Elevator.archived_at.is_(None))
    if yard_id is not None:
        stmt = stmt.where(Building.yard_id == yard_id)
    if building_id is not None:
        stmt = stmt.where(Elevator.building_id == building_id)
    if status is not None:
        stmt = stmt.where(Elevator.current_status == validate_status(status))
    if only_commissioned is not None:
        stmt = stmt.where(Elevator.is_commissioned.is_(only_commissioned))
    if FLAG_NO_CONTRACT in flags:
        stmt = stmt.where(_no_contract(today))
    if FLAG_CERT_EXPIRED in flags:
        stmt = stmt.where(_cert_expired(today))
    if FLAG_MAINTENANCE_OVERDUE in flags:
        stmt = stmt.where(_maintenance_overdue_exists(today))
    return stmt


def _registry_base(selection) -> Select:
    return select(selection).join(Building, Elevator.building_id == Building.id)


async def list_elevators_async(
    db: AsyncSession,
    *,
    yard_id: int | None = None,
    building_id: int | None = None,
    status: str | None = None,
    only_commissioned: bool | None = None,
    include_archived: bool = False,
    flags: set[str] | None = None,
    limit: int = 200,
    offset: int = 0,
    now: datetime | None = None,
) -> list[Elevator]:
    """Страница реестра (дом подгружен), порядок: адрес дома, подъезд, номер.

    ``flags`` ⊆ {no_contract, cert_expired, maintenance_overdue}: договор/
    освидетельствование отсутствуют или истекли на бизнес-«сегодня»; ТО
    просрочено — есть planned-запись старше ``MAINTENANCE_OVERDUE_GRACE_DAYS``.
    """
    if not 1 <= limit <= MAX_PAGE or offset < 0:
        raise ElevatorValidationError(f"limit 1..{MAX_PAGE}, offset ≥ 0")
    stmt = _apply_registry_filters(
        _registry_base(Elevator).options(selectinload(Elevator.building)),
        yard_id=yard_id, building_id=building_id, status=status,
        only_commissioned=only_commissioned, include_archived=include_archived,
        flags=_validate_flags(flags), today=today_of(now),
    )
    stmt = (
        stmt.order_by(Building.address, Elevator.entrance_number, Elevator.elevator_number, Elevator.id)
        .limit(limit)
        .offset(offset)
    )
    return list((await db.execute(stmt)).scalars().all())


async def count_elevators_async(
    db: AsyncSession,
    *,
    yard_id: int | None = None,
    building_id: int | None = None,
    status: str | None = None,
    only_commissioned: bool | None = None,
    include_archived: bool = False,
    flags: set[str] | None = None,
    now: datetime | None = None,
) -> int:
    """Число лифтов под теми же фильтрами, что ``list_elevators_async`` (для пагинации)."""
    stmt = _apply_registry_filters(
        _registry_base(func.count(Elevator.id)),
        yard_id=yard_id, building_id=building_id, status=status,
        only_commissioned=only_commissioned, include_archived=include_archived,
        flags=_validate_flags(flags), today=today_of(now),
    )
    return int((await db.execute(stmt)).scalar_one())


# ---------------------------------------------------------------------------
# Сводка
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Row:
    elevator_id: int
    status: str | None
    status_since: datetime | None
    contract_until: date | None
    cert_valid_until: date | None
    yard_id: int
    yard_name: str


def _is_downtime_over(row: _Row, now: datetime, thresholds: Mapping[str, Any]) -> bool:
    if row.status not in DOWNTIME_STATUSES or row.status_since is None:
        return False
    return downtime_threshold_reached(row.status, as_utc(row.status_since), now, thresholds)


def _counters(
    rows: Sequence[_Row], *, today: date, now: datetime,
    overdue_ids: frozenset[int], thresholds: Mapping[str, Any],
) -> ElevatorCounters:
    by_status = Counter(row.status for row in rows if row.status is not None)
    return ElevatorCounters(
        total=len(rows),
        by_status=MappingProxyType(dict(sorted(by_status.items()))),
        no_contract=sum(1 for r in rows if r.contract_until is None or r.contract_until < today),
        cert_expired=sum(1 for r in rows if r.cert_valid_until is None or r.cert_valid_until < today),
        maintenance_overdue=sum(1 for r in rows if r.elevator_id in overdue_ids),
        downtime_over_threshold=sum(1 for r in rows if _is_downtime_over(r, now, thresholds)),
    )


async def _load_summary_rows(db: AsyncSession) -> list[_Row]:
    stmt = (
        select(
            Elevator.id, Elevator.current_status, Elevator.status_since,
            Elevator.contract_until, Elevator.cert_valid_until, Building.yard_id, Yard.name,
        )
        .join(Building, Elevator.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
        .where(Elevator.archived_at.is_(None))
        .order_by(Yard.name, Yard.id)
    )
    return [_Row(*row) for row in (await db.execute(stmt)).all()]


async def _load_overdue_ids(db: AsyncSession, today: date) -> frozenset[int]:
    stmt = select(ElevatorMaintenanceOccurrence.elevator_id.distinct()).where(
        ElevatorMaintenanceOccurrence.kind == "maintenance",
        ElevatorMaintenanceOccurrence.state == "planned",
        ElevatorMaintenanceOccurrence.due_on < _overdue_cutoff(today),
    )
    return frozenset((await db.execute(stmt)).scalars().all())


async def count_elevator_requests_without_elevator_async(db: AsyncSession) -> int:
    """Открытые заявки категории «лифт» без привязанного лифта (дефицит данных)."""
    stmt = select(func.count(Request.request_number)).where(
        Request.category == ELEVATOR_CATEGORY,
        Request.elevator_id.is_(None),
        Request.status.not_in(list(TERMINAL_STATUSES)),
    )
    return int((await db.execute(stmt)).scalar_one())


async def summary_async(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    downtime_thresholds: Mapping[str, Any] | None = None,
) -> ElevatorSummary:
    """Сводка по активным лифтам: итого и по дворам (дворы в порядке названий).

    ``downtime_thresholds`` — секция ``downtime_threshold_days`` конфига
    (``None`` = дефолты): лифт считается «в простое дольше порога», если
    ``downtime_threshold_reached``.
    """
    now = now_or_utc(now)
    today = today_of(now)
    thresholds = (
        downtime_thresholds if downtime_thresholds is not None
        else DEFAULT_ELEVATORS_CONFIG["downtime_threshold_days"]
    )
    rows = await _load_summary_rows(db)
    overdue_ids = await _load_overdue_ids(db, today)
    requests_without = await count_elevator_requests_without_elevator_async(db)

    def counters_for(subset: Sequence[_Row]) -> ElevatorCounters:
        return _counters(subset, today=today, now=now, overdue_ids=overdue_ids, thresholds=thresholds)

    yards: dict[int, tuple[str, list[_Row]]] = {}
    for row in rows:
        yards.setdefault(row.yard_id, (row.yard_name, []))[1].append(row)
    return ElevatorSummary(
        today=today,
        totals=counters_for(rows),
        yards=tuple(
            YardElevatorSummary(yard_id=yard_id, yard_name=name, counters=counters_for(subset))
            for yard_id, (name, subset) in yards.items()
        ),
        requests_without_elevator=requests_without,
    )
