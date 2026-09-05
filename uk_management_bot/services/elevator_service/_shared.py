"""Общие хелперы DB-слоя сервиса «Лифты» (T3): время, JSON-снимки, события журнала.

Без сессий: строители возвращают новые объекты, ``session.add`` делают обёртки.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from uk_management_bot.database.models.elevator import (
    ELEVATOR_EVENT_KINDS,
    ELEVATOR_EVENT_SOURCES,
    ElevatorStatusEvent,
)
from uk_management_bot.utils.business_time import business_today
from uk_management_bot.utils.datetime_utils import utc_now

from ._core import ElevatorValidationError, require_aware

# Источник событий, порождённых действиями персонала над паспортом/графиком
MANUAL_SOURCE = "manual"


def now_or_utc(now: datetime | None) -> datetime:
    """``now`` из параметра (обязан быть tz-aware) или текущий UTC-инстант."""
    return require_aware(now, "now") if now is not None else utc_now()


def today_of(now: datetime | None) -> date:
    """Бизнес-дата для ``now`` (или для текущего момента)."""
    return business_today(now)


def validate_source(source: str) -> str:
    """Источник события ∈ ``ELEVATOR_EVENT_SOURCES``, иначе ``ElevatorValidationError``."""
    if source not in ELEVATOR_EVENT_SOURCES:
        raise ElevatorValidationError(
            f"неизвестный источник события {source!r}; допустимо: {', '.join(ELEVATOR_EVENT_SOURCES)}"
        )
    return source


def jsonable(value: Any) -> Any:
    """Значение поля → JSON-совместимое (даты в ISO); остальное как есть."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def new_event(
    elevator_id: int,
    kind: str,
    *,
    now: datetime,
    actor_user_id: int | None,
    source: str = MANUAL_SOURCE,
    old_status: str | None = None,
    new_status: str | None = None,
    request_number: str | None = None,
    reason: str | None = None,
    payload: Mapping[str, Any] | None = None,
) -> ElevatorStatusEvent:
    """Новая строка журнала (не добавлена в сессию). ``kind`` — из канона модели."""
    if kind not in ELEVATOR_EVENT_KINDS:
        raise ElevatorValidationError(f"неизвестный вид события журнала {kind!r}")
    return ElevatorStatusEvent(
        elevator_id=elevator_id,
        event_kind=kind,
        old_status=old_status,
        new_status=new_status,
        occurred_at=now,
        actor_user_id=actor_user_id,
        source=validate_source(source),
        request_number=request_number,
        reason=reason,
        payload=dict(payload) if payload is not None else None,
    )
