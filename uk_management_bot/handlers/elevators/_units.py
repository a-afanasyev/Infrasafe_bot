"""Sync-юниты бота лифтёра (Ф5, T10): DB-фаза под ``run_db``, без aiogram.

Каждый юнит начинается с ``check_access``: флаг модуля, approved-пользователь,
роль ``executor`` (``check_user_role_sync``) и специализация ``elevator``
(``parse_specializations`` резолвит алиас ``maintenance``). Наружу выходят
только frozen-DTO; ORM за границу run_db не выходит. Commit/rollback — здесь,
отправка сообщений — у вызывающего (после commit).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Mapping, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.elevator import Elevator, ElevatorMaintenanceOccurrence
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.elevator_service import (
    ElevatorConflictError,
    ElevatorNotFoundError,
    ElevatorValidationError,
    availability_30d,
    complete_occurrence_sync,
    count_open_requests_by_elevator_sync,
    elevator_label,
    get_elevator_sync,
    get_occurrence_sync,
    list_active_for_building_sync,
    list_occurrences_sync,
    load_config_sync,
    set_status_sync,
    status_intervals_sync,
)
from uk_management_bot.utils.auth_helpers import check_user_role_sync
from uk_management_bot.utils.business_time import business_today
from uk_management_bot.utils.datetime_utils import utc_now
from uk_management_bot.utils.specializations import parse_specializations

logger = logging.getLogger(__name__)

REQUIRED_ROLE = "executor"
REQUIRED_SPECIALIZATION = "elevator"
MANUAL_SOURCE = "manual"
PLANNED = "planned"
# Кнопка «Отметить ТО выполненным» — если есть planned-пункт с due_on ≤ сегодня + N дней.
DUE_SOON_DAYS = 7

OK = "ok"


# ══════════════════════════════════════════════════════════════════════════
# DTO — пересекают границу run_db
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Access:
    """Вердикт доступа: ok | disabled | no_access | no_spec."""

    verdict: str
    user_id: Optional[int] = None


@dataclass(frozen=True)
class YardRow:
    id: int
    name: str


@dataclass(frozen=True)
class YardsView:
    verdict: str
    yards: tuple[YardRow, ...] = ()


@dataclass(frozen=True)
class BuildingRow:
    id: int
    address: str
    elevators: int


@dataclass(frozen=True)
class BuildingsView:
    verdict: str  # ok | not_found | вердикт доступа
    yard_id: int = 0
    yard_name: str = ""
    buildings: tuple[BuildingRow, ...] = ()


@dataclass(frozen=True)
class ElevatorRow:
    id: int
    entrance: int
    number: int
    status: Optional[str]


@dataclass(frozen=True)
class ElevatorsView:
    verdict: str
    building_id: int = 0
    yard_id: int = 0
    address: str = ""
    elevators: tuple[ElevatorRow, ...] = ()


@dataclass(frozen=True)
class CardView:
    verdict: str
    id: int = 0
    building_id: int = 0
    label: str = ""
    status: Optional[str] = None
    status_since: Optional[datetime] = None
    is_commissioned: bool = False
    availability: Optional[float] = None
    next_kind: Optional[str] = None
    next_due: Optional[date] = None
    open_requests: int = 0
    can_complete: bool = False


@dataclass(frozen=True)
class StatusOutcome:
    verdict: str  # changed | unchanged | not_found | rejected | вердикт доступа
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    messages: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class OccurrenceRow:
    id: int
    kind: str
    due_on: date
    overdue: bool


@dataclass(frozen=True)
class OccurrencesView:
    verdict: str
    elevator_id: int = 0
    rows: tuple[OccurrenceRow, ...] = ()


@dataclass(frozen=True)
class OccurrenceTarget:
    verdict: str  # ok | not_found | state_error | вердикт доступа
    id: int = 0
    elevator_id: int = 0
    kind: str = ""


@dataclass(frozen=True)
class CompleteOutcome:
    verdict: str  # done | not_found | state_error | invalid | вердикт доступа
    elevator_id: int = 0
    next_due: Optional[date] = None


# ══════════════════════════════════════════════════════════════════════════
# Гейт
# ══════════════════════════════════════════════════════════════════════════


def check_access(db: Session, telegram_id: int) -> Access:
    """Флаг модуля → approved-пользователь → роль executor → специализация «лифты»."""
    if not settings.ELEVATORS_ENABLED:
        return Access("disabled")
    user = db.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
    if user is None or user.status != "approved":
        return Access("no_access")
    if not check_user_role_sync(user.id, REQUIRED_ROLE, db):
        return Access("no_spec", user.id)
    if REQUIRED_SPECIALIZATION not in parse_specializations(user):
        return Access("no_spec", user.id)
    return Access(OK, user.id)


# ══════════════════════════════════════════════════════════════════════════
# Навигация: дворы → дома → лифты
# ══════════════════════════════════════════════════════════════════════════


def load_yards(db: Session, telegram_id: int) -> YardsView:
    access = check_access(db, telegram_id)
    if access.verdict != OK:
        return YardsView(access.verdict)
    yards = db.execute(select(Yard).where(Yard.is_active.is_(True)).order_by(Yard.name)).scalars().all()
    return YardsView(OK, tuple(YardRow(y.id, y.name) for y in yards))


def _elevator_counts(db: Session, yard_id: int) -> dict[int, int]:
    stmt = (
        select(Elevator.building_id, func.count(Elevator.id))
        .join(Building, Building.id == Elevator.building_id)
        .where(Building.yard_id == yard_id, Elevator.archived_at.is_(None))
        .group_by(Elevator.building_id)
    )
    return {int(building_id): int(count) for building_id, count in db.execute(stmt).all()}


def load_buildings(db: Session, telegram_id: int, yard_id: int) -> BuildingsView:
    access = check_access(db, telegram_id)
    if access.verdict != OK:
        return BuildingsView(access.verdict)
    yard = db.get(Yard, yard_id)
    if yard is None or not yard.is_active:
        return BuildingsView("not_found")
    counts = _elevator_counts(db, yard_id)
    buildings = db.execute(
        select(Building)
        .where(Building.yard_id == yard_id, Building.is_active.is_(True))
        .order_by(Building.address)
    ).scalars().all()
    rows = tuple(BuildingRow(b.id, b.address, counts.get(b.id, 0)) for b in buildings)
    return BuildingsView(OK, yard.id, yard.name, rows)


def load_elevators(db: Session, telegram_id: int, building_id: int) -> ElevatorsView:
    access = check_access(db, telegram_id)
    if access.verdict != OK:
        return ElevatorsView(access.verdict)
    building = db.get(Building, building_id)
    if building is None or not building.is_active:
        return ElevatorsView("not_found")
    rows = tuple(
        ElevatorRow(e.id, e.entrance_number, e.elevator_number, e.current_status)
        for e in list_active_for_building_sync(db, building_id)
    )
    return ElevatorsView(OK, building.id, building.yard_id, building.address, rows)


# ══════════════════════════════════════════════════════════════════════════
# Карточка
# ══════════════════════════════════════════════════════════════════════════


def _availability(db: Session, elevator: Elevator) -> Optional[float]:
    intervals = status_intervals_sync(db, [elevator.id]).get(elevator.id, ())
    return availability_30d(elevator, intervals, now=utc_now())


def _planned(db: Session, elevator_id: int) -> list[ElevatorMaintenanceOccurrence]:
    return list_occurrences_sync(db, elevator_id, state=PLANNED)


def load_card(db: Session, telegram_id: int, elevator_id: int, language: str) -> CardView:
    access = check_access(db, telegram_id)
    if access.verdict != OK:
        return CardView(access.verdict)
    try:
        elevator = get_elevator_sync(db, elevator_id)
    except ElevatorNotFoundError:
        return CardView("not_found")
    planned = _planned(db, elevator.id)
    due_limit = business_today() + timedelta(days=DUE_SOON_DAYS)
    nearest = planned[0] if planned else None
    return CardView(
        OK, id=elevator.id, building_id=elevator.building_id,
        label=elevator_label(elevator, language), status=elevator.current_status,
        status_since=elevator.status_since, is_commissioned=bool(elevator.is_commissioned),
        availability=_availability(db, elevator),
        next_kind=nearest.kind if nearest else None, next_due=nearest.due_on if nearest else None,
        open_requests=count_open_requests_by_elevator_sync(db, [elevator.id]).get(elevator.id, 0),
        can_complete=any(o.due_on <= due_limit for o in planned),
    )


# ══════════════════════════════════════════════════════════════════════════
# Смена статуса
# ══════════════════════════════════════════════════════════════════════════


def apply_status(
    db: Session, telegram_id: int, elevator_id: int, status: str, *,
    reason: Optional[str], request_number: Optional[str],
) -> StatusOutcome:
    """``set_status_sync(source="manual")`` + commit; сообщения жителям возвращаются."""
    access = check_access(db, telegram_id)
    if access.verdict != OK:
        return StatusOutcome(access.verdict)
    try:
        change = set_status_sync(
            db, elevator_id, status, actor_user_id=access.user_id, source=MANUAL_SOURCE,
            reason=reason, request_number=request_number, config=load_config_sync(db),
        )
    except ElevatorNotFoundError:
        return StatusOutcome("not_found")
    except (ElevatorConflictError, ElevatorValidationError) as exc:
        db.rollback()
        logger.info("Статус лифта %s отклонён (лифтёр tg=%s): %s", elevator_id, telegram_id, exc)
        return StatusOutcome("rejected")
    if not change.changed:
        return StatusOutcome("unchanged", change.old_status, change.new_status)
    db.commit()
    return StatusOutcome(
        "changed", change.old_status, change.new_status,
        tuple((m.telegram_id, m.text) for m in change.resident_messages),
    )


# ══════════════════════════════════════════════════════════════════════════
# График: список planned, выбор, закрытие
# ══════════════════════════════════════════════════════════════════════════


def load_occurrences(db: Session, telegram_id: int, elevator_id: int) -> OccurrencesView:
    access = check_access(db, telegram_id)
    if access.verdict != OK:
        return OccurrencesView(access.verdict)
    try:
        elevator = get_elevator_sync(db, elevator_id)
    except ElevatorNotFoundError:
        return OccurrencesView("not_found")
    today = business_today()
    rows = tuple(
        OccurrenceRow(o.id, o.kind, o.due_on, o.due_on < today) for o in _planned(db, elevator.id)
    )
    return OccurrencesView(OK, elevator.id, rows)


def load_occurrence(db: Session, telegram_id: int, occurrence_id: int) -> OccurrenceTarget:
    access = check_access(db, telegram_id)
    if access.verdict != OK:
        return OccurrenceTarget(access.verdict)
    try:
        occurrence = get_occurrence_sync(db, occurrence_id)
    except ElevatorNotFoundError:
        return OccurrenceTarget("not_found")
    if occurrence.state != PLANNED:
        return OccurrenceTarget("state_error")
    return OccurrenceTarget(OK, occurrence.id, occurrence.elevator_id, occurrence.kind)


def complete_occurrence(
    db: Session, telegram_id: int, occurrence_id: int, *,
    comment: Optional[str], cert_fields: Optional[Mapping[str, Any]],
) -> CompleteOutcome:
    """``complete_occurrence_sync`` + commit; ``next_due`` — ближайший planned того же вида."""
    access = check_access(db, telegram_id)
    if access.verdict != OK:
        return CompleteOutcome(access.verdict)
    try:
        occurrence = complete_occurrence_sync(
            db, occurrence_id, actor_user_id=access.user_id, comment=comment, cert_fields=cert_fields,
        )
    except ElevatorNotFoundError:
        return CompleteOutcome("not_found")
    except ElevatorConflictError:
        db.rollback()
        return CompleteOutcome("state_error")
    except ElevatorValidationError as exc:
        db.rollback()
        logger.info("Закрытие пункта графика %s отклонено (tg=%s): %s", occurrence_id, telegram_id, exc)
        return CompleteOutcome("invalid")
    elevator_id, kind = occurrence.elevator_id, occurrence.kind
    db.commit()
    upcoming = list_occurrences_sync(db, elevator_id, kind=kind, state=PLANNED)
    return CompleteOutcome("done", elevator_id, upcoming[0].due_on if upcoming else None)
