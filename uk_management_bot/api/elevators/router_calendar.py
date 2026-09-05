"""График ТО/освидетельствований лифтов (под-роутер /api/v2/elevators).

Включается в основной роутер модуля ДО его динамических ``/{elevator_id}``-путей:
статичный ``GET /occurrences`` иначе перехватывался бы ``GET /{elevator_id}``.
Флаг-гейт наследуется от основного роутера при include; маппинг доменных
ошибок — общий ``errors.http_error``.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_approved_roles
from uk_management_bot.api.elevators import calendar_service
from uk_management_bot.api.elevators.errors import http_error
from uk_management_bot.api.elevators.schemas import (
    CalendarState,
    ElevatorOccurrenceCompleteIn,
    ElevatorOccurrenceCreateIn,
    ElevatorOccurrenceGenerateIn,
    ElevatorOccurrenceOut,
    ElevatorOccurrenceRescheduleIn,
    Lang,
    OccurrenceKind,
    OccurrenceState,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.services.elevator_service import ElevatorServiceError

router = APIRouter()

_staff = require_approved_roles("executor", "manager")
_manager_only = require_approved_roles("manager")


# ── Статичные пути (ДО /{elevator_id}) ───────────────────────────────

@router.get("/occurrences", response_model=list[ElevatorOccurrenceOut])
async def calendar_all(
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    state: CalendarState = Query("planned"),
    kind: Optional[OccurrenceKind] = Query(None),
    lang: Lang = Query("ru"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_staff),
):
    """Календарь всех лифтов за период (даты включительно); ``state=all`` — без фильтра."""
    try:
        return await calendar_service.calendar(
            db, from_date=from_date, to_date=to_date,
            state=None if state == "all" else state, kind=kind, language=lang,
        )
    except ElevatorServiceError as exc:
        raise http_error(exc)


@router.patch("/occurrences/{occurrence_id}", response_model=ElevatorOccurrenceOut)
async def reschedule_occurrence(
    occurrence_id: int,
    body: ElevatorOccurrenceRescheduleIn,
    lang: Lang = Query("ru"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    try:
        return await calendar_service.reschedule_tx(
            db, occurrence_id, due_on=body.due_on, actor_user_id=user.id, language=lang
        )
    except ElevatorServiceError as exc:
        raise http_error(exc)


@router.post("/occurrences/{occurrence_id}/cancel", response_model=ElevatorOccurrenceOut)
async def cancel_occurrence(
    occurrence_id: int,
    lang: Lang = Query("ru"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    try:
        return await calendar_service.cancel_tx(db, occurrence_id, actor_user_id=user.id, language=lang)
    except ElevatorServiceError as exc:
        raise http_error(exc)


@router.post("/occurrences/{occurrence_id}/complete", response_model=ElevatorOccurrenceOut)
async def complete_occurrence(
    occurrence_id: int,
    body: ElevatorOccurrenceCompleteIn,
    lang: Lang = Query("ru"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_staff),
):
    """Закрыть запись; освидетельствование обновляет паспорт (номер/срок/акт)."""
    try:
        return await calendar_service.complete_tx(
            db, occurrence_id, body, actor_user_id=user.id, language=lang
        )
    except ElevatorServiceError as exc:
        raise http_error(exc)


# ── График одного лифта ──────────────────────────────────────────────

@router.get("/{elevator_id}/occurrences", response_model=list[ElevatorOccurrenceOut])
async def list_occurrences(
    elevator_id: int,
    kind: Optional[OccurrenceKind] = Query(None),
    state: Optional[OccurrenceState] = Query(None),
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    lang: Lang = Query("ru"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_staff),
):
    try:
        return await calendar_service.list_for_elevator(
            db, elevator_id, kind=kind, state=state, from_date=from_date, to_date=to_date,
            language=lang,
        )
    except ElevatorServiceError as exc:
        raise http_error(exc)


@router.post("/{elevator_id}/occurrences", response_model=ElevatorOccurrenceOut, status_code=201)
async def create_occurrence(
    elevator_id: int,
    body: ElevatorOccurrenceCreateIn,
    lang: Lang = Query("ru"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    try:
        return await calendar_service.create_tx(
            db, elevator_id, kind=body.kind, due_on=body.due_on, actor_user_id=user.id, language=lang
        )
    except ElevatorServiceError as exc:
        raise http_error(exc)


@router.post(
    "/{elevator_id}/occurrences/generate",
    response_model=list[ElevatorOccurrenceOut],
    status_code=201,
)
async def generate_occurrences(
    elevator_id: int,
    body: ElevatorOccurrenceGenerateIn,
    lang: Lang = Query("ru"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    """Сгенерировать график с шагом в месяцах; существующие даты пропускаются (идемпотентно)."""
    try:
        return await calendar_service.generate_tx(
            db, elevator_id, kind=body.kind, start=body.start, every_months=body.every_months,
            count=body.count, actor_user_id=user.id, language=lang,
        )
    except ElevatorServiceError as exc:
        raise http_error(exc)
