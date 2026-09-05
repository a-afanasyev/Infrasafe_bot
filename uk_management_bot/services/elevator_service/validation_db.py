"""Валидация на границе DB-слоя: ширина колонок, формат номера заявки, URL, причина,
привязка заявки к лифту (Р11 с запросом в БД).

Длины берутся из ``Elevator.__table__`` — констант-дублей нет: расширили
колонку в модели/миграции — валидатор подхватил сам.

``resolve_request_elevator_*`` — ЕДИНСТВЕННАЯ точка проверки Р11 для всех
конструкторов заявок (бот sync, API TWA/инспектор, колл-центр, InfraSafe):
чистый ``require_elevator_for_category`` + «лифт существует, не архивирован,
введён в эксплуатацию (и, если задано, принадлежит дому заявки)».
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import String, Table
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.elevator import Elevator
from uk_management_bot.services.request_number_service import REQUEST_NUMBER_PATTERN

from ._core import ElevatorNotFoundError, ElevatorValidationError
from .reads import (
    get_elevator_including_archived_async,
    get_elevator_including_archived_sync,
)
from .validation import require_elevator_for_category

MAX_REASON_LEN = 500
ALLOWED_URL_SCHEMES: tuple[str, ...] = ("http://", "https://")
_REQUEST_NUMBER_RE = re.compile(REQUEST_NUMBER_PATTERN)


def validate_string_lengths(fields: Mapping[str, Any], table: Table = Elevator.__table__) -> None:
    """Строковые поля ≤ ширины колонки; не-строка в ``String``-колонке → ошибка.

    Поля вне таблицы и ``Text``-колонки (без длины) не проверяются.
    """
    problems = []
    for name, value in fields.items():
        column = table.columns.get(name)
        if column is None or value is None or not isinstance(column.type, String):
            continue
        if not isinstance(value, str):
            problems.append(f"{name}: ожидается строка")
        elif column.type.length is not None and len(value) > column.type.length:
            problems.append(f"{name}: не длиннее {column.type.length} символов")
    if problems:
        raise ElevatorValidationError("; ".join(problems))


def validate_request_number(value: str | None) -> str | None:
    """``None`` или номер заявки формата ``YYMMDD-NNN`` (канон ``RequestNumberService``)."""
    if value is None:
        return None
    if not isinstance(value, str) or not _REQUEST_NUMBER_RE.match(value):
        raise ElevatorValidationError(f"некорректный номер заявки {value!r}")
    return value


def validate_url(value: str | None, name: str, *, max_len: int | None) -> str | None:
    """Только ``http://``/``https://`` и не длиннее ``max_len`` (ширина колонки)."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.lower().startswith(ALLOWED_URL_SCHEMES):
        raise ElevatorValidationError(f"{name}: допустимы только ссылки http:// или https://")
    if max_len is not None and len(value) > max_len:
        raise ElevatorValidationError(f"{name}: не длиннее {max_len} символов")
    return value


def validate_reason(value: str | None) -> str | None:
    """Причина — строка не длиннее ``MAX_REASON_LEN`` (или ``None``)."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ElevatorValidationError("reason: ожидается строка")
    if len(value) > MAX_REASON_LEN:
        raise ElevatorValidationError(f"reason: не длиннее {MAX_REASON_LEN} символов")
    return value


def cert_act_url_max_len() -> int | None:
    return Elevator.__table__.columns["cert_act_url"].type.length


def validate_passport_values(fields: Mapping[str, Any]) -> None:
    """Границы паспорта/договора/освидетельствования: длины + схема ``cert_act_url``."""
    validate_string_lengths(fields)
    if "cert_act_url" in fields:
        validate_url(fields["cert_act_url"], "cert_act_url", max_len=cert_act_url_max_len())


# ---------------------------------------------------------------------------
# Привязка заявки к лифту (Р11) — общая для всех конструкторов заявок
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RequestElevator:
    """Что писать в ``requests.elevator_id``/``elevator_operational``.

    ``elevator`` — загруженный лифт (с домом) для подписи в ответе; ``None``
    вместе с обоими полями, когда флаг выключен или лифт не указан.
    """

    elevator_id: int | None
    elevator_operational: bool | None
    elevator: Elevator | None


UNBOUND_ELEVATOR = RequestElevator(elevator_id=None, elevator_operational=None, elevator=None)


def _check_usable(elevator: Elevator, *, building_id: int | None) -> Elevator:
    """Архивный / невведённый / чужого дома → ``ElevatorValidationError``."""
    if elevator.archived_at is not None:
        raise ElevatorValidationError(f"лифт {elevator.id} архивирован")
    if not elevator.is_commissioned:
        raise ElevatorValidationError(f"лифт {elevator.id} не введён в эксплуатацию")
    if building_id is not None and elevator.building_id != building_id:
        raise ElevatorValidationError(f"лифт {elevator.id} относится к другому дому")
    return elevator


def ensure_elevator_usable_sync(
    db: Session, elevator_id: int, *, building_id: int | None = None
) -> Elevator:
    """Лифт, к которому можно привязать заявку; иначе ``ElevatorValidationError``.

    Неизвестный id — тоже ``ElevatorValidationError`` (а не NotFound): это
    некорректный ввод создающего заявку, а не отсутствующий ресурс URL.
    """
    try:
        elevator = get_elevator_including_archived_sync(db, elevator_id)
    except ElevatorNotFoundError as exc:
        raise ElevatorValidationError(str(exc)) from exc
    return _check_usable(elevator, building_id=building_id)


async def ensure_elevator_usable_async(
    db: AsyncSession, elevator_id: int, *, building_id: int | None = None
) -> Elevator:
    """Async-зеркало ``ensure_elevator_usable_sync``."""
    try:
        elevator = await get_elevator_including_archived_async(db, elevator_id)
    except ElevatorNotFoundError as exc:
        raise ElevatorValidationError(str(exc)) from exc
    return _check_usable(elevator, building_id=building_id)


def _binding(elevator: Elevator, elevator_operational: bool | None) -> RequestElevator:
    return RequestElevator(
        elevator_id=elevator.id, elevator_operational=elevator_operational, elevator=elevator
    )


def resolve_request_elevator_sync(
    db: Session,
    *,
    category: str | None,
    elevator_id: int | None,
    elevator_operational: bool | None,
    enabled: bool,
    building_id: int | None = None,
) -> RequestElevator:
    """Р11 для конструкторов заявок (sync, бот).

    Флаг выключен → поля игнорируются (``UNBOUND_ELEVATOR``, в БД NULL).
    Категория «лифт» без полей → ``ElevatorValidationError`` (чистый валидатор).
    Лифт указан (любая категория) → обязан быть пригодным
    (``ensure_elevator_usable_sync``); ``building_id`` — доп. требование
    «лифт этого дома» (InfraSafe).
    """
    require_elevator_for_category(category, elevator_id, elevator_operational, enabled=enabled)
    if not enabled or elevator_id is None:
        return UNBOUND_ELEVATOR
    elevator = ensure_elevator_usable_sync(db, elevator_id, building_id=building_id)
    return _binding(elevator, elevator_operational)


async def resolve_request_elevator_async(
    db: AsyncSession,
    *,
    category: str | None,
    elevator_id: int | None,
    elevator_operational: bool | None,
    enabled: bool,
    building_id: int | None = None,
) -> RequestElevator:
    """Async-зеркало ``resolve_request_elevator_sync`` (API, InfraSafe)."""
    require_elevator_for_category(category, elevator_id, elevator_operational, enabled=enabled)
    if not enabled or elevator_id is None:
        return UNBOUND_ELEVATOR
    elevator = await ensure_elevator_usable_async(db, elevator_id, building_id=building_id)
    return _binding(elevator, elevator_operational)
