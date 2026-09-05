"""``set_status``: единственный путь смены статуса лифта (бот sync / API async).

Строитель ``_build_status_change`` общий; обёртки различаются только загрузкой
лифта (``FOR UPDATE``) и адресатов. Адресаты запрашиваются только когда для
нового статуса есть уведомление и оно включено в конфиге. Сообщения
возвращаются, не отправляются; текст HTML-безопасен (адрес дома экранирован)
— слать с parse_mode=HTML. Commit — у вызывающего.
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.elevator import Elevator, ElevatorStatusEvent
from uk_management_bot.utils.address_helpers import localize_address
from uk_management_bot.utils.helpers import get_text

from ._core import Message, StatusChange
from ._shared import DEFAULT_LANGUAGE, new_event, now_or_utc, validate_source
from .reads import get_elevator_async, get_elevator_sync
from .recipients import Recipient, residents_of_entrance_async, residents_of_entrance_sync
from .reminder_rules import DEFAULT_ELEVATORS_CONFIG
from .validation import can_set_status, validate_status
from .validation_db import validate_reason, validate_request_number

# Новый статус → флаг конфига resident_notifications и ключ локали
_RESIDENT_NOTIFY_KEYS: Mapping[str, str] = {
    "under_repair": "repair_started",
    "maintenance": "maintenance_started",
    "working": "back_in_service",
}
_LOCALE_PREFIX = "elevators.notify."


def resident_notify_key(new_status: str | None, config: Mapping[str, Any] | None) -> str | None:
    """Ключ уведомления жителям для статуса, если оно есть и включено; иначе ``None``."""
    key = _RESIDENT_NOTIFY_KEYS.get(new_status or "")
    if key is None:
        return None
    source = config if config is not None else DEFAULT_ELEVATORS_CONFIG
    flags = source.get("resident_notifications") or {}
    return key if bool(flags.get(key, True)) else None


def _resident_text(elevator: Elevator, notify_key: str, language: str) -> str:
    address = localize_address(elevator.building.address or "", language)
    return get_text(
        _LOCALE_PREFIX + notify_key,
        language=language,
        building=html.escape(address),
        entrance=elevator.entrance_number,
        elevator=elevator.elevator_number,
    )


def build_resident_messages(
    elevator: Elevator,
    new_status: str,
    recipients: Sequence[Recipient],
    config: Mapping[str, Any] | None,
) -> tuple[Message, ...]:
    """Сообщения жителям подъезда по новому статусу (пусто для ``not_working``/выключенного)."""
    notify_key = resident_notify_key(new_status, config)
    if notify_key is None:
        return ()
    return tuple(
        Message(
            telegram_id=recipient.telegram_id,
            text=_resident_text(elevator, notify_key, recipient.language or DEFAULT_LANGUAGE),
        )
        for recipient in recipients
    )


def _build_status_change(
    elevator: Elevator,
    new_status: str,
    *,
    actor_user_id: int | None,
    source: str,
    reason: str | None,
    request_number: str | None,
    now: datetime,
) -> tuple[StatusChange, ElevatorStatusEvent | None]:
    """Применить смену статуса к загруженному лифту; событие — если статус изменился.

    Идемпотентный повтор того же статуса: ``changed=False``, лифт не тронут.
    """
    status = validate_status(new_status)
    validate_source(source)
    validate_reason(reason)
    validate_request_number(request_number)
    can_set_status(
        status, is_commissioned=bool(elevator.is_commissioned),
        archived=elevator.archived_at is not None,
    )
    old_status = elevator.current_status
    if old_status == status:
        return (
            StatusChange(
                changed=False, elevator_id=elevator.id, old_status=old_status,
                new_status=status, status_since=elevator.status_since,
            ),
            None,
        )
    elevator.current_status = status
    elevator.status_since = now
    elevator.downtime_reminded_at = None
    elevator.version = (elevator.version or 1) + 1
    event = new_event(
        elevator.id, "status_changed", now=now, actor_user_id=actor_user_id, source=source,
        old_status=old_status, new_status=status, request_number=request_number, reason=reason,
    )
    change = StatusChange(
        changed=True, elevator_id=elevator.id, old_status=old_status,
        new_status=status, status_since=now,
    )
    return change, event


def _with_messages(
    change: StatusChange, elevator: Elevator, recipients: Sequence[Recipient],
    config: Mapping[str, Any] | None,
) -> StatusChange:
    messages = build_resident_messages(elevator, change.new_status or "", recipients, config)
    return replace(change, resident_messages=messages)


def set_status_sync(
    db: Session,
    elevator_id: int,
    new_status: str,
    *,
    actor_user_id: int | None,
    source: str,
    reason: str | None = None,
    request_number: str | None = None,
    now: datetime | None = None,
    config: Mapping[str, Any] | None = None,
) -> StatusChange:
    """Сменить статус лифта (бот). Лифт под ``FOR UPDATE``; commit — у вызывающего.

    ``config`` — конфиг модуля (``load_config_sync``); ``None`` = дефолты.
    """
    now = now_or_utc(now)
    elevator = get_elevator_sync(db, elevator_id, for_update=True)
    change, event = _build_status_change(
        elevator, new_status, actor_user_id=actor_user_id, source=source,
        reason=reason, request_number=request_number, now=now,
    )
    if event is None:
        return change
    db.add(event)
    db.flush()
    if resident_notify_key(change.new_status, config) is None:
        return change
    recipients = residents_of_entrance_sync(db, elevator.building_id, elevator.entrance_number)
    return _with_messages(change, elevator, recipients, config)


async def set_status_async(
    db: AsyncSession,
    elevator_id: int,
    new_status: str,
    *,
    actor_user_id: int | None,
    source: str,
    reason: str | None = None,
    request_number: str | None = None,
    now: datetime | None = None,
    config: Mapping[str, Any] | None = None,
) -> StatusChange:
    """Async-зеркало ``set_status_sync`` (API)."""
    now = now_or_utc(now)
    elevator = await get_elevator_async(db, elevator_id, for_update=True)
    change, event = _build_status_change(
        elevator, new_status, actor_user_id=actor_user_id, source=source,
        reason=reason, request_number=request_number, now=now,
    )
    if event is None:
        return change
    db.add(event)
    await db.flush()
    if resident_notify_key(change.new_status, config) is None:
        return change
    recipients = await residents_of_entrance_async(
        db, elevator.building_id, elevator.entrance_number
    )
    return _with_messages(change, elevator, recipients, config)
