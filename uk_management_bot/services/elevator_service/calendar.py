"""График ТО / освидетельствований: генерация, ручные пункты, перенос, отмена, закрытие.

Даты считает чистое ``generate_occurrence_dates``; здесь — запросы и запись.
Закрытие освидетельствования обновляет паспорт лифта (номер/срок/акт) и
пишет ``cert_changed``; закрытие ТО журнал не трогает — достаточно записи
графика. Commit — у вызывающего.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.elevator import (
    OCCURRENCE_KINDS,
    Elevator,
    ElevatorMaintenanceOccurrence,
    ElevatorStatusEvent,
)

from ._core import ElevatorConflictError, ElevatorValidationError, require_aware
from ._shared import jsonable, new_event, now_or_utc
from .calendar_rules import assert_occurrence_editable, generate_occurrence_dates
from .reads import get_elevator_async, get_elevator_sync, get_occurrence_async, get_occurrence_sync

KIND_CERTIFICATION = "certification"
CERT_REQUIRED_FIELDS: tuple[str, ...] = ("cert_number", "cert_valid_until")
CERT_OPTIONAL_FIELDS: tuple[str, ...] = ("cert_act_url",)


# ---------------------------------------------------------------------------
# Чистые проверки и строители
# ---------------------------------------------------------------------------

def _validate_kind(kind: str) -> str:
    if kind not in OCCURRENCE_KINDS:
        raise ElevatorValidationError(f"неизвестный вид работ {kind!r}; допустимо: {', '.join(OCCURRENCE_KINDS)}")
    return kind


def _active_dates_stmt(elevator_id: int, kind: str, dates: Iterable[date], exclude_id: int | None = None) -> Select:
    """``due_on`` неотменённых записей лифта данного вида среди ``dates``."""
    stmt = select(ElevatorMaintenanceOccurrence.due_on).where(
        ElevatorMaintenanceOccurrence.elevator_id == elevator_id,
        ElevatorMaintenanceOccurrence.kind == kind,
        ElevatorMaintenanceOccurrence.due_on.in_(list(dates)),
        ElevatorMaintenanceOccurrence.state != "cancelled",
    )
    if exclude_id is not None:
        stmt = stmt.where(ElevatorMaintenanceOccurrence.id != exclude_id)
    return stmt


def _new_occurrence(elevator_id: int, kind: str, due_on: date, actor_user_id: int | None) -> ElevatorMaintenanceOccurrence:
    return ElevatorMaintenanceOccurrence(
        elevator_id=elevator_id, kind=kind, due_on=due_on, state="planned",
        created_by_user_id=actor_user_id,
    )


def _duplicate(kind: str, due_on: date) -> ElevatorConflictError:
    return ElevatorConflictError(f"запись графика {kind} на {due_on.isoformat()} уже есть")


def _missing_occurrences(
    elevator_id: int, kind: str, dates: Iterable[date], existing: Iterable[date], actor_user_id: int | None
) -> list[ElevatorMaintenanceOccurrence]:
    taken = set(existing)
    return [_new_occurrence(elevator_id, kind, day, actor_user_id) for day in dates if day not in taken]


def _validate_cert_fields(kind: str, cert_fields: Mapping[str, Any] | None) -> dict[str, Any]:
    """Для освидетельствования обязательны номер и срок; для ТО поля запрещены."""
    if kind != KIND_CERTIFICATION:
        if cert_fields:
            raise ElevatorValidationError("cert_fields допустимы только для освидетельствования")
        return {}
    fields = dict(cert_fields or {})
    unknown = sorted(set(fields) - set(CERT_REQUIRED_FIELDS) - set(CERT_OPTIONAL_FIELDS))
    if unknown:
        raise ElevatorValidationError(f"недопустимые поля освидетельствования: {', '.join(unknown)}")
    missing = [name for name in CERT_REQUIRED_FIELDS if not fields.get(name)]
    if missing:
        raise ElevatorValidationError("для освидетельствования обязательны: " + ", ".join(missing))
    if not isinstance(fields["cert_valid_until"], date):
        raise ElevatorValidationError("cert_valid_until: ожидается дата")
    return fields


def _apply_cert(
    elevator: Elevator, fields: Mapping[str, Any], *, now: datetime,
    actor_user_id: int | None, request_number: str | None,
) -> ElevatorStatusEvent:
    changed = {}
    for name in (*CERT_REQUIRED_FIELDS, *CERT_OPTIONAL_FIELDS):
        if name in fields:
            changed[name] = [jsonable(getattr(elevator, name)), jsonable(fields[name])]
            setattr(elevator, name, fields[name])
    elevator.cert_reminder_stage = 0
    elevator.version = (elevator.version or 1) + 1
    return new_event(elevator.id, "cert_changed", now=now, actor_user_id=actor_user_id,
                     request_number=request_number, payload={"changed": changed})


def _apply_completion(
    occurrence: ElevatorMaintenanceOccurrence, elevator: Elevator, *,
    actor_user_id: int | None, comment: str | None, done_at: datetime | None,
    cert_fields: Mapping[str, Any] | None, request_number: str | None, now: datetime,
) -> ElevatorStatusEvent | None:
    """Закрыть запись графика; для освидетельствования — обновить паспорт и вернуть событие."""
    assert_occurrence_editable(occurrence.state)
    fields = _validate_cert_fields(occurrence.kind, cert_fields)
    occurrence.state = "done"
    occurrence.done_at = require_aware(done_at, "done_at") if done_at is not None else now
    occurrence.done_by_user_id = actor_user_id
    occurrence.comment = comment
    occurrence.request_number = request_number
    if occurrence.kind != KIND_CERTIFICATION:
        return None
    return _apply_cert(elevator, fields, now=now, actor_user_id=actor_user_id, request_number=request_number)


# ---------------------------------------------------------------------------
# SYNC (бот)
# ---------------------------------------------------------------------------

def generate_occurrences_sync(
    db: Session, elevator_id: int, *, kind: str, start: date, every_months: int, count: int,
    actor_user_id: int | None,
) -> list[ElevatorMaintenanceOccurrence]:
    """Сгенерировать график; уже существующие даты пропускаются, возвращаются созданные."""
    _validate_kind(kind)
    elevator = get_elevator_sync(db, elevator_id)
    dates = generate_occurrence_dates(start, every_months, count)
    existing = db.execute(_active_dates_stmt(elevator.id, kind, dates)).scalars().all()
    created = _missing_occurrences(elevator.id, kind, dates, existing, actor_user_id)
    db.add_all(created)
    db.flush()
    return created


def create_occurrence_sync(
    db: Session, elevator_id: int, *, kind: str, due_on: date, actor_user_id: int | None
) -> ElevatorMaintenanceOccurrence:
    """Один пункт графика; дубль даты → ``ElevatorConflictError``."""
    _validate_kind(kind)
    elevator = get_elevator_sync(db, elevator_id)
    if db.execute(_active_dates_stmt(elevator.id, kind, [due_on])).first() is not None:
        raise _duplicate(kind, due_on)
    occurrence = _new_occurrence(elevator.id, kind, due_on, actor_user_id)
    db.add(occurrence)
    db.flush()
    return occurrence


def complete_occurrence_sync(
    db: Session, occurrence_id: int, *, actor_user_id: int | None, comment: str | None,
    done_at: datetime | None = None, cert_fields: Mapping[str, Any] | None = None,
    request_number: str | None = None, now: datetime | None = None,
) -> ElevatorMaintenanceOccurrence:
    """Закрыть запись графика (см. ``_apply_completion``)."""
    now = now_or_utc(now)
    occurrence = get_occurrence_sync(db, occurrence_id, for_update=True)
    elevator = get_elevator_sync(db, occurrence.elevator_id, for_update=True)
    event = _apply_completion(
        occurrence, elevator, actor_user_id=actor_user_id, comment=comment, done_at=done_at,
        cert_fields=cert_fields, request_number=request_number, now=now,
    )
    if event is not None:
        db.add(event)
    db.flush()
    return occurrence


# ---------------------------------------------------------------------------
# ASYNC (API)
# ---------------------------------------------------------------------------

async def generate_occurrences_async(
    db: AsyncSession, elevator_id: int, *, kind: str, start: date, every_months: int, count: int,
    actor_user_id: int | None,
) -> list[ElevatorMaintenanceOccurrence]:
    """Async-зеркало ``generate_occurrences_sync``."""
    _validate_kind(kind)
    elevator = await get_elevator_async(db, elevator_id)
    dates = generate_occurrence_dates(start, every_months, count)
    existing = (await db.execute(_active_dates_stmt(elevator.id, kind, dates))).scalars().all()
    created = _missing_occurrences(elevator.id, kind, dates, existing, actor_user_id)
    db.add_all(created)
    await db.flush()
    return created


async def create_occurrence_async(
    db: AsyncSession, elevator_id: int, *, kind: str, due_on: date, actor_user_id: int | None
) -> ElevatorMaintenanceOccurrence:
    """Async-зеркало ``create_occurrence_sync``."""
    _validate_kind(kind)
    elevator = await get_elevator_async(db, elevator_id)
    if (await db.execute(_active_dates_stmt(elevator.id, kind, [due_on]))).first() is not None:
        raise _duplicate(kind, due_on)
    occurrence = _new_occurrence(elevator.id, kind, due_on, actor_user_id)
    db.add(occurrence)
    await db.flush()
    return occurrence


async def reschedule_occurrence_async(
    db: AsyncSession, occurrence_id: int, *, due_on: date, actor_user_id: int | None
) -> ElevatorMaintenanceOccurrence:
    """Перенести planned-запись: новая дата, стадии напоминаний сброшены."""
    occurrence = await get_occurrence_async(db, occurrence_id, for_update=True)
    assert_occurrence_editable(occurrence.state)
    if occurrence.due_on == due_on:
        return occurrence
    taken = await db.execute(_active_dates_stmt(occurrence.elevator_id, occurrence.kind, [due_on], occurrence.id))
    if taken.first() is not None:
        raise _duplicate(occurrence.kind, due_on)
    occurrence.due_on = due_on
    occurrence.reminder_stage = 0
    occurrence.overdue_reminded_at = None
    await db.flush()
    return occurrence


async def cancel_occurrence_async(
    db: AsyncSession, occurrence_id: int, *, actor_user_id: int | None
) -> ElevatorMaintenanceOccurrence:
    """Отменить planned-запись (done/cancelled → ``ElevatorStateError``)."""
    occurrence = await get_occurrence_async(db, occurrence_id, for_update=True)
    assert_occurrence_editable(occurrence.state)
    occurrence.state = "cancelled"
    await db.flush()
    return occurrence


async def complete_occurrence_async(
    db: AsyncSession, occurrence_id: int, *, actor_user_id: int | None, comment: str | None,
    done_at: datetime | None = None, cert_fields: Mapping[str, Any] | None = None,
    request_number: str | None = None, now: datetime | None = None,
) -> ElevatorMaintenanceOccurrence:
    """Async-зеркало ``complete_occurrence_sync``."""
    now = now_or_utc(now)
    occurrence = await get_occurrence_async(db, occurrence_id, for_update=True)
    elevator = await get_elevator_async(db, occurrence.elevator_id, for_update=True)
    event = _apply_completion(
        occurrence, elevator, actor_user_id=actor_user_id, comment=comment, done_at=done_at,
        cert_fields=cert_fields, request_number=request_number, now=now,
    )
    if event is not None:
        db.add(event)
    await db.flush()
    return occurrence
