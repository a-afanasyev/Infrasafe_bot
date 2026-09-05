"""API-сервис-слой графика ТО/освидетельствований лифтов.

Транзакционные обёртки над ``services/elevator_service.calendar`` (+ commit)
и сборка ответов с подписью лифта. Записи после commit перечитываются
(``refresh``) — server-default ``created_at`` иначе не загружен.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.elevator import ElevatorMaintenanceOccurrence
from uk_management_bot.services import elevator_service as domain

from . import presenters
from .schemas import ElevatorOccurrenceCompleteIn, ElevatorOccurrenceOut

CERT_FIELDS: tuple[str, ...] = ("cert_number", "cert_valid_until", "cert_act_url")


async def _label_for(db: AsyncSession, elevator_id: int, *, language: str) -> str:
    elevator = await domain.get_elevator_including_archived_async(db, elevator_id)
    return domain.elevator_label(elevator, language)


async def _refreshed_out(
    db: AsyncSession, occurrence: ElevatorMaintenanceOccurrence, *, language: str
) -> ElevatorOccurrenceOut:
    await db.refresh(occurrence)
    label = await _label_for(db, occurrence.elevator_id, language=language)
    return presenters.build_occurrence(occurrence, label)


def _outs(rows: list[ElevatorMaintenanceOccurrence], label: str) -> list[ElevatorOccurrenceOut]:
    return [presenters.build_occurrence(row, label) for row in rows]


# ── Чтение ───────────────────────────────────────────────────────────

async def list_for_elevator(
    db: AsyncSession, elevator_id: int, *, kind: str | None, state: str | None,
    from_date: date | None, to_date: date | None, language: str,
) -> list[ElevatorOccurrenceOut]:
    label = await _label_for(db, elevator_id, language=language)  # 404, если лифта нет
    rows = await domain.list_occurrences_async(
        db, elevator_id, kind=kind, state=state, from_date=from_date, to_date=to_date
    )
    return _outs(rows, label)


async def calendar(
    db: AsyncSession, *, from_date: date, to_date: date, state: str | None, kind: str | None,
    language: str,
) -> list[ElevatorOccurrenceOut]:
    """Календарь всех лифтов за период; ``kind`` фильтруется по загруженным строкам."""
    rows = await domain.list_all_occurrences_async(db, from_date=from_date, to_date=to_date, state=state)
    return [
        presenters.build_occurrence(row, domain.elevator_label(row.elevator, language))
        for row in rows
        if kind is None or row.kind == kind
    ]


# ── Запись ───────────────────────────────────────────────────────────

async def create_tx(
    db: AsyncSession, elevator_id: int, *, kind: str, due_on: date, actor_user_id: int, language: str,
) -> ElevatorOccurrenceOut:
    occurrence = await domain.create_occurrence_async(
        db, elevator_id, kind=kind, due_on=due_on, actor_user_id=actor_user_id
    )
    await db.commit()
    return await _refreshed_out(db, occurrence, language=language)


async def generate_tx(
    db: AsyncSession, elevator_id: int, *, kind: str, start: date, every_months: int, count: int,
    actor_user_id: int, language: str,
) -> list[ElevatorOccurrenceOut]:
    """Сгенерировать график; возвращаются только созданные записи (идемпотентно)."""
    created = await domain.generate_occurrences_async(
        db, elevator_id, kind=kind, start=start, every_months=every_months, count=count,
        actor_user_id=actor_user_id,
    )
    await db.commit()
    for occurrence in created:
        await db.refresh(occurrence)
    return _outs(created, await _label_for(db, elevator_id, language=language))


async def reschedule_tx(
    db: AsyncSession, occurrence_id: int, *, due_on: date, actor_user_id: int, language: str,
) -> ElevatorOccurrenceOut:
    occurrence = await domain.reschedule_occurrence_async(
        db, occurrence_id, due_on=due_on, actor_user_id=actor_user_id
    )
    await db.commit()
    return await _refreshed_out(db, occurrence, language=language)


async def cancel_tx(
    db: AsyncSession, occurrence_id: int, *, actor_user_id: int, language: str,
) -> ElevatorOccurrenceOut:
    occurrence = await domain.cancel_occurrence_async(db, occurrence_id, actor_user_id=actor_user_id)
    await db.commit()
    return await _refreshed_out(db, occurrence, language=language)


def cert_fields_of(body: ElevatorOccurrenceCompleteIn) -> Mapping[str, Any] | None:
    """Поля освидетельствования из тела (только переданные); ``None`` — не переданы."""
    fields = body.model_dump(include=set(CERT_FIELDS), exclude_unset=True)
    return fields or None


async def complete_tx(
    db: AsyncSession, occurrence_id: int, body: ElevatorOccurrenceCompleteIn, *,
    actor_user_id: int, language: str,
) -> ElevatorOccurrenceOut:
    occurrence = await domain.complete_occurrence_async(
        db, occurrence_id, actor_user_id=actor_user_id, comment=body.comment,
        done_at=body.done_at, cert_fields=cert_fields_of(body), request_number=body.request_number,
    )
    await db.commit()
    return await _refreshed_out(db, occurrence, language=language)
