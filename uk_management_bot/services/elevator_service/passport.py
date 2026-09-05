"""Паспорт лифта: создание, правка, ввод в эксплуатацию, архивация.

Общие строители (``_apply_*``) работают с уже загруженными объектами и
возвращают новые события журнала; sync/async-обёртки делают запросы и
запись через ``flush_or_conflict_*`` (уникальные констрейнты → 409).
Commit — у вызывающего.

Политика:

* при создании журнал не пишется (``created_at`` достаточно);
* ``passport_changed`` — только по реально изменившимся полям; смена
  ``contract_until``/``cert_valid_until`` дополнительно даёт
  ``contract_changed``/``cert_changed`` и сбрасывает стадию напоминаний;
* место лифта (дом/подъезд/номер) меняется только до ввода в эксплуатацию;
  дубль места ловится констрейнтом ``uq_elevators_building_entrance_number_active``;
* ``commissioned_at`` правится только через ``commission`` (не patch);
* архив: статус остаётся как есть (историческая правда), planned-записи
  графика отменяются, публичность снимается.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from sqlalchemy import Update, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.elevator import (
    Elevator,
    ElevatorMaintenanceOccurrence,
    ElevatorStatusEvent,
)

from ._core import ElevatorConflictError, ElevatorStateError, ElevatorValidationError
from ._shared import (
    PLACE_UNIQUE,
    PUBLIC_CODE_UNIQUE,
    ConflictResolver,
    conflict_for,
    flush_or_conflict_async,
    flush_or_conflict_sync,
    jsonable,
    new_event,
    now_or_utc,
    today_of,
    violates,
)
from .public_code import generate_public_code
from .reads import (
    get_elevator_async,
    get_elevator_including_archived_async,
    get_elevator_including_archived_sync,
    get_elevator_sync,
)
from .validation import PASSPORT_REQUIRED_FIELDS, validate_passport_required
from .validation_db import validate_passport_values, validate_reason

PLACE_FIELDS: tuple[str, ...] = ("building_id", "entrance_number", "elevator_number")
PASSPORT_FIELDS: tuple[str, ...] = (
    "passport_number", "manufacturer", "serial_number", "factory_number",
    "model", "production_year", "capacity_kg", "floors_served",
)
CONTRACT_FIELDS: tuple[str, ...] = (
    "service_org_name", "service_org_phone", "contract_number", "contract_until",
)
CERT_FIELDS: tuple[str, ...] = ("cert_number", "cert_valid_until", "cert_act_url")
DOWNTIME_FIELDS: tuple[str, ...] = (
    "downtime_reason", "spare_part_expected_on", "publish_downtime_details",
)
# Разрешённые поля создания/правки паспорта (единый набор)
EDITABLE_FIELDS: frozenset[str] = frozenset(
    (*PLACE_FIELDS, *PASSPORT_FIELDS, *CONTRACT_FIELDS, *CERT_FIELDS, *DOWNTIME_FIELDS, "is_public")
)
# Поле → (вид события, колонка стадии напоминаний), сбрасываемая при смене даты
_DATE_EVENTS: Mapping[str, tuple[str, str]] = {
    "contract_until": ("contract_changed", "contract_reminder_stage"),
    "cert_valid_until": ("cert_changed", "cert_reminder_stage"),
}
COMMISSIONED_STATUS = "working"
MAX_PUBLIC_CODE_ATTEMPTS = 5


class _PublicCodeCollision(ElevatorConflictError):
    """Внутренний маркер: занят ``public_code`` — сгенерировать новый и повторить."""


# ---------------------------------------------------------------------------
# Чистые проверки и строители
# ---------------------------------------------------------------------------

def _validate_fields(fields: Mapping[str, Any]) -> None:
    unknown = sorted(set(fields) - EDITABLE_FIELDS)
    if unknown:
        raise ElevatorValidationError(f"недопустимые поля паспорта: {', '.join(unknown)}")
    validate_passport_values(fields)


def _check_building(building: Building | None, building_id: int, entrance_number: int) -> None:
    """Дом существует и активен; подъезд не превышает ``entrance_count`` (если задан)."""
    if building is None or not building.is_active:
        raise ElevatorValidationError(f"дом {building_id} не найден или неактивен")
    if building.entrance_count and entrance_number > building.entrance_count:
        raise ElevatorValidationError(
            f"в доме {building.entrance_count} подъездов, подъезд {entrance_number} невозможен"
        )


def _place_conflict(place: Mapping[str, Any]) -> ElevatorConflictError:
    return ElevatorConflictError(
        "лифт №{elevator_number} в подъезде {entrance_number} дома {building_id} уже есть".format(**place)
    )


def _on_create_integrity_error(exc: IntegrityError, data: Mapping[str, Any]) -> ElevatorConflictError | None:
    """Создание: занятый ``public_code`` → ретрай, дубль места → 409, иное → не наше."""
    if violates(exc, PUBLIC_CODE_UNIQUE):
        return _PublicCodeCollision("public_code занят")
    if violates(exc, PLACE_UNIQUE):
        return _place_conflict(data)
    return None


def _new_elevator(data: Mapping[str, Any], public_code: str) -> Elevator:
    return Elevator(
        **{field: data.get(field) for field in EDITABLE_FIELDS if field in data},
        public_code=public_code, current_status=None, is_commissioned=False,
    )


def _diff(elevator: Elevator, patch: Mapping[str, Any]) -> dict[str, tuple[Any, Any]]:
    """Реально изменившиеся поля: ``{field: (old, new)}`` (без мутации)."""
    return {
        field: (getattr(elevator, field), value)
        for field, value in patch.items()
        if getattr(elevator, field) != value
    }


def _guard_patch(
    elevator: Elevator, patch: Mapping[str, Any], expected_version: int | None
) -> dict[str, tuple[Any, Any]]:
    """Проверки правки; пустой diff → ``{}`` ДО проверки версии (no-op не конфликтует)."""
    _validate_fields(patch)
    diff = _diff(elevator, patch)
    if not diff:
        return {}
    if expected_version is not None and elevator.version != expected_version:
        raise ElevatorConflictError(
            f"карточка лифта {elevator.id} изменена другим пользователем (версия {elevator.version})"
        )
    if elevator.is_commissioned and any(field in diff for field in PLACE_FIELDS):
        raise ElevatorStateError("после ввода в эксплуатацию дом/подъезд/номер лифта не меняются")
    merged = {field: patch.get(field, getattr(elevator, field)) for field in PASSPORT_REQUIRED_FIELDS}
    validate_passport_required(merged)
    return diff


def _new_place(elevator: Elevator, diff: Mapping[str, tuple[Any, Any]]) -> dict[str, Any] | None:
    """Новое место лифта, если patch его меняет; иначе ``None``."""
    if not any(field in diff for field in PLACE_FIELDS):
        return None
    return {field: diff[field][1] if field in diff else getattr(elevator, field) for field in PLACE_FIELDS}


def _passport_events(
    elevator_id: int, diff: Mapping[str, tuple[Any, Any]], *, now: datetime, actor_user_id: int | None
) -> list[ElevatorStatusEvent]:
    """События по diff (чистая: лифт не трогает)."""
    changed = {field: [jsonable(old), jsonable(new)] for field, (old, new) in diff.items()}
    events = [new_event(elevator_id, "passport_changed", now=now, actor_user_id=actor_user_id,
                        payload={"changed": changed})]
    for field, (kind, _stage_attr) in _DATE_EVENTS.items():
        if field in diff:
            events.append(new_event(elevator_id, kind, now=now, actor_user_id=actor_user_id,
                                    payload={field: changed[field]}))
    return events


def _apply_patch(
    elevator: Elevator, diff: Mapping[str, tuple[Any, Any]], *, now: datetime, actor_user_id: int | None
) -> list[ElevatorStatusEvent]:
    """Применить diff, сбросить стадии напоминаний по изменённым датам, поднять версию."""
    for field, (_, new) in diff.items():
        setattr(elevator, field, new)
    for field, (_kind, stage_attr) in _DATE_EVENTS.items():
        if field in diff:
            setattr(elevator, stage_attr, 0)
    elevator.version = (elevator.version or 1) + 1
    return _passport_events(elevator.id, diff, now=now, actor_user_id=actor_user_id)


def _apply_commission(
    elevator: Elevator, *, commissioned_at: date | None, now: datetime, actor_user_id: int | None
) -> list[ElevatorStatusEvent]:
    if elevator.is_commissioned:
        raise ElevatorStateError(f"лифт {elevator.id} уже введён в эксплуатацию")
    validate_passport_required({f: getattr(elevator, f) for f in PASSPORT_REQUIRED_FIELDS})
    day = commissioned_at if commissioned_at is not None else today_of(now)
    elevator.is_commissioned = True
    elevator.commissioned_at = day
    elevator.current_status = COMMISSIONED_STATUS
    elevator.status_since = now
    elevator.version = (elevator.version or 1) + 1
    return [
        new_event(elevator.id, "commissioned", now=now, actor_user_id=actor_user_id,
                  payload={"commissioned_at": day.isoformat()}),
        new_event(elevator.id, "status_changed", now=now, actor_user_id=actor_user_id,
                  old_status=None, new_status=COMMISSIONED_STATUS),
    ]


def _apply_archive(
    elevator: Elevator, *, reason: str, now: datetime, actor_user_id: int | None
) -> ElevatorStatusEvent:
    if elevator.archived_at is not None:
        raise ElevatorStateError(f"лифт {elevator.id} уже архивирован")
    if not (validate_reason(reason) or "").strip():
        raise ElevatorValidationError("укажите причину архивации")
    elevator.archived_at = now
    elevator.archived_reason = reason.strip()
    elevator.is_public = False
    elevator.version = (elevator.version or 1) + 1
    return new_event(elevator.id, "archived", now=now, actor_user_id=actor_user_id, reason=reason.strip())


def _cancel_planned_stmt(elevator_id: int) -> Update:
    return (
        update(ElevatorMaintenanceOccurrence)
        .where(
            ElevatorMaintenanceOccurrence.elevator_id == elevator_id,
            ElevatorMaintenanceOccurrence.state == "planned",
        )
        .values(state="cancelled")
        .execution_options(synchronize_session="fetch")
    )


def _place_resolver(place: Mapping[str, Any] | None) -> ConflictResolver:
    """Место менялось → дубль места = 409; иначе любая IntegrityError — не наша."""
    if place is None:
        return lambda exc: None
    return conflict_for(PLACE_UNIQUE, _place_conflict(place))


def _exhausted() -> ElevatorConflictError:
    return ElevatorConflictError("не удалось подобрать уникальный public_code, повторите")


# ---------------------------------------------------------------------------
# SYNC (бот)
# ---------------------------------------------------------------------------

def create_elevator_sync(db: Session, data: Mapping[str, Any], *, actor_user_id: int | None) -> Elevator:
    """Завести лифт: паспорт обязателен, дом активен, место свободно, код уникален."""
    validate_passport_required(data)
    _validate_fields(data)
    _check_building(db.get(Building, data["building_id"]), data["building_id"], data["entrance_number"])
    for _ in range(MAX_PUBLIC_CODE_ATTEMPTS):
        try:
            [elevator] = flush_or_conflict_sync(
                db, lambda: [_new_elevator(data, generate_public_code())],
                on_conflict=lambda exc: _on_create_integrity_error(exc, data),
            )
        except _PublicCodeCollision:
            continue
        return elevator
    raise _exhausted()


def update_passport_sync(
    db: Session, elevator_id: int, patch: Mapping[str, Any], *,
    actor_user_id: int | None, expected_version: int | None, now: datetime | None = None,
) -> Elevator:
    """Правка паспорта с оптимистичной блокировкой; пустой/пустой по факту patch — no-op."""
    now = now_or_utc(now)
    elevator = get_elevator_sync(db, elevator_id, for_update=True)
    diff = _guard_patch(elevator, patch, expected_version)
    if not diff:
        return elevator
    place = _new_place(elevator, diff)
    if place is not None:
        _check_building(db.get(Building, place["building_id"]), place["building_id"], place["entrance_number"])
    flush_or_conflict_sync(
        db, lambda: _apply_patch(elevator, diff, now=now, actor_user_id=actor_user_id),
        on_conflict=_place_resolver(place),
    )
    return elevator


def commission_sync(
    db: Session, elevator_id: int, *, actor_user_id: int | None,
    commissioned_at: date | None = None, now: datetime | None = None,
) -> Elevator:
    """Ввод в эксплуатацию: статус ``working``, события ``commissioned`` + ``status_changed``."""
    now = now_or_utc(now)
    elevator = get_elevator_sync(db, elevator_id, for_update=True)
    db.add_all(_apply_commission(elevator, commissioned_at=commissioned_at, now=now, actor_user_id=actor_user_id))
    db.flush()
    return elevator


def archive_sync(
    db: Session, elevator_id: int, *, actor_user_id: int | None, reason: str, now: datetime | None = None
) -> Elevator:
    """Архивировать лифт; planned-записи графика отменяются; повтор → ``ElevatorStateError``."""
    now = now_or_utc(now)
    elevator = get_elevator_including_archived_sync(db, elevator_id, for_update=True)
    db.add(_apply_archive(elevator, reason=reason, now=now, actor_user_id=actor_user_id))
    db.execute(_cancel_planned_stmt(elevator.id))
    db.flush()
    return elevator


# ---------------------------------------------------------------------------
# ASYNC (API) — зеркала sync, различие только в await
# ---------------------------------------------------------------------------

async def create_elevator_async(
    db: AsyncSession, data: Mapping[str, Any], *, actor_user_id: int | None
) -> Elevator:
    """Async-зеркало ``create_elevator_sync``."""
    validate_passport_required(data)
    _validate_fields(data)
    building = await db.get(Building, data["building_id"])
    _check_building(building, data["building_id"], data["entrance_number"])
    for _ in range(MAX_PUBLIC_CODE_ATTEMPTS):
        try:
            [elevator] = await flush_or_conflict_async(
                db, lambda: [_new_elevator(data, generate_public_code())],
                on_conflict=lambda exc: _on_create_integrity_error(exc, data),
            )
        except _PublicCodeCollision:
            continue
        return elevator
    raise _exhausted()


async def update_passport_async(
    db: AsyncSession, elevator_id: int, patch: Mapping[str, Any], *,
    actor_user_id: int | None, expected_version: int | None, now: datetime | None = None,
) -> Elevator:
    """Async-зеркало ``update_passport_sync``."""
    now = now_or_utc(now)
    elevator = await get_elevator_async(db, elevator_id, for_update=True)
    diff = _guard_patch(elevator, patch, expected_version)
    if not diff:
        return elevator
    place = _new_place(elevator, diff)
    if place is not None:
        building = await db.get(Building, place["building_id"])
        _check_building(building, place["building_id"], place["entrance_number"])
    await flush_or_conflict_async(
        db, lambda: _apply_patch(elevator, diff, now=now, actor_user_id=actor_user_id),
        on_conflict=_place_resolver(place),
    )
    return elevator


async def commission_async(
    db: AsyncSession, elevator_id: int, *, actor_user_id: int | None,
    commissioned_at: date | None = None, now: datetime | None = None,
) -> Elevator:
    """Async-зеркало ``commission_sync``."""
    now = now_or_utc(now)
    elevator = await get_elevator_async(db, elevator_id, for_update=True)
    db.add_all(_apply_commission(elevator, commissioned_at=commissioned_at, now=now, actor_user_id=actor_user_id))
    await db.flush()
    return elevator


async def archive_async(
    db: AsyncSession, elevator_id: int, *, actor_user_id: int | None, reason: str,
    now: datetime | None = None,
) -> Elevator:
    """Async-зеркало ``archive_sync``."""
    now = now_or_utc(now)
    elevator = await get_elevator_including_archived_async(db, elevator_id, for_update=True)
    db.add(_apply_archive(elevator, reason=reason, now=now, actor_user_id=actor_user_id))
    await db.execute(_cancel_planned_stmt(elevator.id))
    await db.flush()
    return elevator
