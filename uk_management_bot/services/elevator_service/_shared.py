"""Общие хелперы DB-слоя сервиса «Лифты» (T3): время, JSON-снимки, события
журнала, единый контракт ``IntegrityError → ElevatorConflictError``.

Без сессий в строителях: они возвращают новые объекты, ``session.add`` делают
обёртки. Единственное исключение — ``flush_or_conflict_*``: точка записи,
которая переводит нарушение уникального констрейнта в доменный 409.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, TypeVar

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.elevator import (
    ELEVATOR_EVENT_KINDS,
    ELEVATOR_EVENT_SOURCES,
    ElevatorStatusEvent,
)
from uk_management_bot.utils.business_time import business_today
from uk_management_bot.utils.datetime_utils import utc_now

from ._core import ElevatorConflictError, ElevatorValidationError, require_aware

# Источник событий, порождённых действиями персонала над паспортом/графиком
MANUAL_SOURCE = "manual"
# Язык уведомлений, если у пользователя не задан
DEFAULT_LANGUAGE = "ru"

T = TypeVar("T")
# Резолвер: какая доменная ошибка соответствует IntegrityError; None = не наша
ConflictResolver = Callable[[IntegrityError], ElevatorConflictError | None]


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


# ---------------------------------------------------------------------------
# IntegrityError → ElevatorConflictError
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UniqueRule:
    """Уникальный констрейнт/индекс: имя в каталоге PG и маркер sqlite-сообщения.

    psycopg2 отдаёт имя в ``exc.orig.diag.constraint_name``; sqlite — только
    текст ``UNIQUE constraint failed: table.col, table.col``.
    """

    name: str
    sqlite_marker: str


# Имена — из alembic/versions/0017_elevators.py и моделей (elevator.py)
PUBLIC_CODE_UNIQUE = UniqueRule("elevators_public_code_key", "elevators.public_code")
PLACE_UNIQUE = UniqueRule(
    "uq_elevators_building_entrance_number_active",
    "elevators.building_id, elevators.entrance_number, elevators.elevator_number",
)
OCCURRENCE_UNIQUE = UniqueRule(
    "uq_elevator_maintenance_occurrences_active",
    "elevator_maintenance_occurrences.elevator_id, elevator_maintenance_occurrences.kind, "
    "elevator_maintenance_occurrences.due_on",
)


def violates(exc: IntegrityError, rule: UniqueRule) -> bool:
    """Нарушен ли именно этот констрейнт (имя из диагностики PG или текст sqlite)."""
    diag = getattr(exc.orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name:
        return constraint_name == rule.name
    text = str(exc.orig)
    return rule.name in text or rule.sqlite_marker in text


def conflict_for(rule: UniqueRule, error: ElevatorConflictError) -> ConflictResolver:
    """Резолвер «одно правило → одна ошибка»; остальные IntegrityError — не наши."""
    return lambda exc: error if violates(exc, rule) else None


def _resolve_or_reraise(exc: IntegrityError, on_conflict: ConflictResolver) -> ElevatorConflictError:
    conflict = on_conflict(exc)
    if conflict is None:
        raise exc
    return conflict


def flush_or_conflict_sync(
    db: Session, apply: Callable[[], Sequence[T]], *, on_conflict: ConflictResolver
) -> Sequence[T]:
    """Выполнить ``apply`` (мутации + новые объекты) и flush внутри savepoint.

    ``apply`` обязан вызываться ВНУТРИ savepoint: ``begin_nested()`` сначала
    сбрасывает уже накопленные изменения (autoflush), и мутация, сделанная до
    него, ушла бы в БД вне savepoint — отказ констрейнта убил бы всю
    транзакцию. Уникальный конфликт → доменный 409 (сессия пригодна дальше:
    ретрай ``public_code``); неопознанная ``IntegrityError`` пробрасывается.
    """
    try:
        with db.begin_nested():
            objects = apply()
            db.add_all(objects)
            db.flush()
        return objects
    except IntegrityError as exc:
        raise _resolve_or_reraise(exc, on_conflict) from exc


async def flush_or_conflict_async(
    db: AsyncSession, apply: Callable[[], Sequence[T]], *, on_conflict: ConflictResolver
) -> Sequence[T]:
    """Async-зеркало ``flush_or_conflict_sync``."""
    try:
        async with db.begin_nested():
            objects = apply()
            db.add_all(objects)
            await db.flush()
        return objects
    except IntegrityError as exc:
        raise _resolve_or_reraise(exc, on_conflict) from exc
