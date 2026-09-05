"""Чтение сущностей модуля «Лифты»: лифт, журнал, график, заявки лифта.

Sync-варианты — для бота (``Session``), async — для API (``AsyncSession``);
условия запросов общие (``_active_elevator_stmt`` и т.п.), различается
только исполнение. Реестр с фильтрами/сводкой — ``registry.py``.

``selectinload(Elevator.building)`` обязателен в каждой выборке лифтов:
карточки читают адрес дома, а lazy-load в async-сессии невозможен.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.elevator import (
    OCCURRENCE_KINDS,
    OCCURRENCE_STATES,
    Elevator,
    ElevatorMaintenanceOccurrence,
    ElevatorStatusEvent,
)
from uk_management_bot.database.models.request import Request
from uk_management_bot.utils.request_workflow import TERMINAL_STATUSES

from ._core import ElevatorNotFoundError, ElevatorValidationError

MAX_EVENTS_PAGE = 500


# ---------------------------------------------------------------------------
# Statements (общие для sync/async)
# ---------------------------------------------------------------------------

def _elevator_stmt(elevator_id: int, *, include_archived: bool, for_update: bool) -> Select:
    stmt = (
        select(Elevator)
        .options(selectinload(Elevator.building))
        .where(Elevator.id == elevator_id)
    )
    if not include_archived:
        stmt = stmt.where(Elevator.archived_at.is_(None))
    return stmt.with_for_update() if for_update else stmt


def _active_for_building_stmt(building_id: int) -> Select:
    return (
        select(Elevator)
        .options(selectinload(Elevator.building))
        .where(Elevator.building_id == building_id, Elevator.archived_at.is_(None))
        .order_by(Elevator.entrance_number, Elevator.elevator_number)
    )


def _occurrence_stmt(occurrence_id: int, *, for_update: bool) -> Select:
    stmt = select(ElevatorMaintenanceOccurrence).where(
        ElevatorMaintenanceOccurrence.id == occurrence_id
    )
    return stmt.with_for_update() if for_update else stmt


def _not_found(elevator_id: int) -> ElevatorNotFoundError:
    return ElevatorNotFoundError(f"лифт {elevator_id} не найден")


def _occurrence_not_found(occurrence_id: int) -> ElevatorNotFoundError:
    return ElevatorNotFoundError(f"запись графика {occurrence_id} не найдена")


# ---------------------------------------------------------------------------
# SYNC (бот)
# ---------------------------------------------------------------------------

def get_elevator_sync(db: Session, elevator_id: int, *, for_update: bool = False) -> Elevator:
    """Активный (неархивный) лифт с домом; иначе ``ElevatorNotFoundError``."""
    stmt = _elevator_stmt(elevator_id, include_archived=False, for_update=for_update)
    elevator = db.execute(stmt).scalar_one_or_none()
    if elevator is None:
        raise _not_found(elevator_id)
    return elevator


def get_elevator_including_archived_sync(
    db: Session, elevator_id: int, *, for_update: bool = False
) -> Elevator:
    """Лифт с домом, включая архивный (чтение карточки/журнала, архивация)."""
    stmt = _elevator_stmt(elevator_id, include_archived=True, for_update=for_update)
    elevator = db.execute(stmt).scalar_one_or_none()
    if elevator is None:
        raise _not_found(elevator_id)
    return elevator


def list_active_for_building_sync(db: Session, building_id: int) -> list[Elevator]:
    """Неархивные лифты дома, порядок: подъезд, номер."""
    return list(db.execute(_active_for_building_stmt(building_id)).scalars().all())


def get_occurrence_sync(
    db: Session, occurrence_id: int, *, for_update: bool = False
) -> ElevatorMaintenanceOccurrence:
    row = db.execute(_occurrence_stmt(occurrence_id, for_update=for_update)).scalar_one_or_none()
    if row is None:
        raise _occurrence_not_found(occurrence_id)
    return row


# ---------------------------------------------------------------------------
# ASYNC (API)
# ---------------------------------------------------------------------------

async def get_elevator_async(
    db: AsyncSession, elevator_id: int, *, for_update: bool = False
) -> Elevator:
    """Async-зеркало ``get_elevator_sync``."""
    stmt = _elevator_stmt(elevator_id, include_archived=False, for_update=for_update)
    elevator = (await db.execute(stmt)).scalar_one_or_none()
    if elevator is None:
        raise _not_found(elevator_id)
    return elevator


async def get_elevator_including_archived_async(
    db: AsyncSession, elevator_id: int, *, for_update: bool = False
) -> Elevator:
    """Async-зеркало ``get_elevator_including_archived_sync``."""
    stmt = _elevator_stmt(elevator_id, include_archived=True, for_update=for_update)
    elevator = (await db.execute(stmt)).scalar_one_or_none()
    if elevator is None:
        raise _not_found(elevator_id)
    return elevator


async def list_active_for_building_async(db: AsyncSession, building_id: int) -> list[Elevator]:
    """Async-зеркало ``list_active_for_building_sync``."""
    return list((await db.execute(_active_for_building_stmt(building_id))).scalars().all())


async def get_elevators_by_ids_async(
    db: AsyncSession, elevator_ids: Iterable[int]
) -> dict[int, Elevator]:
    """``{id: лифт с домом}`` для страницы заявок — один запрос, включая архивные.

    Карточка заявки обязана показать подпись лифта и после его архивации:
    привязка ``requests.elevator_id`` историческая, а не «текущий реестр».
    """
    ids = {int(i) for i in elevator_ids}
    if not ids:
        return {}
    stmt = (
        select(Elevator)
        .options(selectinload(Elevator.building))
        .where(Elevator.id.in_(ids))
    )
    return {e.id: e for e in (await db.execute(stmt)).scalars().all()}


async def get_occurrence_async(
    db: AsyncSession, occurrence_id: int, *, for_update: bool = False
) -> ElevatorMaintenanceOccurrence:
    stmt = _occurrence_stmt(occurrence_id, for_update=for_update)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise _occurrence_not_found(occurrence_id)
    return row


async def list_events_async(
    db: AsyncSession, elevator_id: int, *, limit: int = 100, before_id: int | None = None
) -> list[ElevatorStatusEvent]:
    """Журнал лифта, новые первые; ``before_id`` — курсор (события с меньшим id)."""
    if not 1 <= limit <= MAX_EVENTS_PAGE:
        raise ElevatorValidationError(f"limit должен быть в диапазоне 1..{MAX_EVENTS_PAGE}")
    stmt = select(ElevatorStatusEvent).where(ElevatorStatusEvent.elevator_id == elevator_id)
    if before_id is not None:
        stmt = stmt.where(ElevatorStatusEvent.id < before_id)
    stmt = stmt.order_by(ElevatorStatusEvent.id.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


def _validate_occurrence_filters(kind: str | None, state: str | None) -> None:
    if kind is not None and kind not in OCCURRENCE_KINDS:
        raise ElevatorValidationError(f"неизвестный вид работ {kind!r}")
    if state is not None and state not in OCCURRENCE_STATES:
        raise ElevatorValidationError(f"неизвестное состояние записи графика {state!r}")


async def list_occurrences_async(
    db: AsyncSession,
    elevator_id: int,
    *,
    kind: str | None = None,
    state: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[ElevatorMaintenanceOccurrence]:
    """График одного лифта по фильтрам, порядок по ``due_on``; даты включительно."""
    _validate_occurrence_filters(kind, state)
    stmt = select(ElevatorMaintenanceOccurrence).where(
        ElevatorMaintenanceOccurrence.elevator_id == elevator_id
    )
    if kind is not None:
        stmt = stmt.where(ElevatorMaintenanceOccurrence.kind == kind)
    if state is not None:
        stmt = stmt.where(ElevatorMaintenanceOccurrence.state == state)
    if from_date is not None:
        stmt = stmt.where(ElevatorMaintenanceOccurrence.due_on >= from_date)
    if to_date is not None:
        stmt = stmt.where(ElevatorMaintenanceOccurrence.due_on <= to_date)
    stmt = stmt.order_by(ElevatorMaintenanceOccurrence.due_on, ElevatorMaintenanceOccurrence.id)
    return list((await db.execute(stmt)).scalars().all())


async def list_all_occurrences_async(
    db: AsyncSession, *, from_date: date, to_date: date, state: str | None = "planned",
    kind: str | None = None,
) -> list[ElevatorMaintenanceOccurrence]:
    """Календарь всех лифтов за период (включительно), лифт с домом подгружен.

    ``state``/``kind`` — фильтры в SQL; ``None`` = без фильтра.
    """
    _validate_occurrence_filters(kind, state)
    if from_date > to_date:
        raise ElevatorValidationError("from_date не может быть позже to_date")
    stmt = (
        select(ElevatorMaintenanceOccurrence)
        .options(
            selectinload(ElevatorMaintenanceOccurrence.elevator).selectinload(Elevator.building)
        )
        .where(
            ElevatorMaintenanceOccurrence.due_on >= from_date,
            ElevatorMaintenanceOccurrence.due_on <= to_date,
        )
    )
    if state is not None:
        stmt = stmt.where(ElevatorMaintenanceOccurrence.state == state)
    if kind is not None:
        stmt = stmt.where(ElevatorMaintenanceOccurrence.kind == kind)
    stmt = stmt.order_by(ElevatorMaintenanceOccurrence.due_on, ElevatorMaintenanceOccurrence.id)
    return list((await db.execute(stmt)).scalars().all())


async def list_requests_for_elevator_async(
    db: AsyncSession, elevator_id: int, *, include_closed: bool = False
) -> list[Request]:
    """Заявки, привязанные к лифту; по умолчанию без терминальных статусов."""
    stmt = select(Request).where(Request.elevator_id == elevator_id)
    if not include_closed:
        stmt = stmt.where(Request.status.not_in(list(TERMINAL_STATUSES)))
    stmt = stmt.order_by(Request.created_at.desc(), Request.request_number.desc())
    return list((await db.execute(stmt)).scalars().all())


async def count_open_requests_by_elevator_async(
    db: AsyncSession, elevator_ids: Sequence[int]
) -> dict[int, int]:
    """``{elevator_id: число нетерминальных заявок}`` для страницы лифтов (один запрос)."""
    if not elevator_ids:
        return {}
    stmt = (
        select(Request.elevator_id, func.count(Request.request_number))
        .where(
            Request.elevator_id.in_(list(elevator_ids)),
            Request.status.not_in(list(TERMINAL_STATUSES)),
        )
        .group_by(Request.elevator_id)
    )
    return {int(elevator_id): int(count) for elevator_id, count in (await db.execute(stmt)).all()}


async def count_building_apartments_without_entrance_async(
    db: AsyncSession, building_id: int
) -> int:
    """Активные квартиры дома без номера подъезда — «дефицит данных» дома.

    Это свойство дома, а не подъезда: без ``entrance`` квартира не попадёт
    ни в один список адресатов, поэтому счётчик показывается на карточке лифта.
    """
    stmt = select(func.count(Apartment.id)).where(
        Apartment.building_id == building_id,
        Apartment.is_active.is_(True),
        Apartment.entrance.is_(None),
    )
    return int((await db.execute(stmt)).scalar_one())
