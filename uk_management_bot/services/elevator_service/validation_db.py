"""Валидация на границе DB-слоя: ширина колонок, формат номера заявки, URL, причина.

Длины берутся из ``Elevator.__table__`` — констант-дублей нет: расширили
колонку в модели/миграции — валидатор подхватил сам.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from sqlalchemy import String, Table

from uk_management_bot.database.models.elevator import Elevator
from uk_management_bot.services.request_number_service import REQUEST_NUMBER_PATTERN

from ._core import ElevatorValidationError

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
