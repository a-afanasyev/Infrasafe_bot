"""Доступность лифта за 30 дней поверх журнала: одна выборка событий на страницу.

Мост между БД и чистым ``compute_availability_30d``: ``Elevator.commissioned_at``
хранится как ``Date`` — конвертируется в полночь бизнес-зоны (UTC-инстант);
инстанты из sqlite приходят naive и нормализуются ``as_utc``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.elevator import Elevator, ElevatorStatusEvent
from uk_management_bot.utils.business_time import business_day_window
from uk_management_bot.utils.datetime_utils import as_utc

from ._shared import now_or_utc
from .availability import StatusInterval, compute_availability_30d

STATUS_EVENT_KIND = "status_changed"


def date_to_business_midnight_utc(day: date) -> datetime:
    """Календарная дата → UTC-инстант полуночи этой даты в бизнес-зоне."""
    return business_day_window(day)[0]


def _intervals_stmt(elevator_ids: Sequence[int]):
    return (
        select(
            ElevatorStatusEvent.elevator_id,
            ElevatorStatusEvent.new_status,
            ElevatorStatusEvent.occurred_at,
        )
        .where(
            ElevatorStatusEvent.elevator_id.in_(list(elevator_ids)),
            ElevatorStatusEvent.event_kind == STATUS_EVENT_KIND,
            ElevatorStatusEvent.new_status.is_not(None),
        )
        .order_by(ElevatorStatusEvent.occurred_at, ElevatorStatusEvent.id)
    )


def _group_intervals(rows) -> dict[int, tuple[StatusInterval, ...]]:
    grouped: dict[int, list[StatusInterval]] = {}
    for elevator_id, new_status, occurred_at in rows:
        grouped.setdefault(elevator_id, []).append(
            StatusInterval(status=new_status, started_at=as_utc(occurred_at))
        )
    return {key: tuple(value) for key, value in grouped.items()}


async def status_intervals_async(
    db: AsyncSession, elevator_ids: Sequence[int]
) -> dict[int, tuple[StatusInterval, ...]]:
    """Интервалы статуса по лифтам из журнала ``status_changed`` (одним запросом).

    Берётся вся история статусов лифта, а не только окно: статус на начало
    окна задаёт последнее событие до него. Смен статуса у лифта — десятки в
    год, для страницы реестра это дёшево.
    """
    if not elevator_ids:
        return {}
    rows = (await db.execute(_intervals_stmt(elevator_ids))).all()
    return _group_intervals(rows)


def availability_30d(
    elevator: Elevator, intervals: Sequence[StatusInterval], *, now: datetime
) -> float | None:
    """Доля времени ``working`` за 30 дней для загруженного лифта (или ``None``)."""
    commissioned_at = (
        date_to_business_midnight_utc(elevator.commissioned_at)
        if elevator.commissioned_at is not None
        else None
    )
    archived_at = as_utc(elevator.archived_at) if elevator.archived_at is not None else None
    return compute_availability_30d(
        intervals, now=now, commissioned_at=commissioned_at, archived_at=archived_at
    )


async def availability_30d_for_page_async(
    db: AsyncSession, elevators: Sequence[Elevator], *, now: datetime | None = None
) -> Mapping[int, float | None]:
    """Доступность для страницы лифтов: ``{elevator_id: доля | None}``, один запрос журнала."""
    now = now_or_utc(now)
    intervals = await status_intervals_async(db, [e.id for e in elevators])
    return {e.id: availability_30d(e, intervals.get(e.id, ()), now=now) for e in elevators}
