"""Напоминания персоналу по лифтам (Ф6): один идемпотентный тик, без сети.

``collect_reminders_sync`` читает график, лифты и адресатов и возвращает
``RemindersBatch``: готовые сообщения (``Message``) и что записать
(``StageAdvance``). ``apply_reminders_sync`` пишет стадии/метки в те же строки.
Вызывающий (планировщик) делает оба шага в одной транзакции, коммитит и лишь
затем отправляет: потеря одного сообщения допустима (Р7), дубль — нет.

Пять видов напоминаний:

1. ТО / освидетельствование по графику — стадии из конфига
   (``staff_reminders.maintenance`` / ``certification``), менеджерам и лифтёрам.
2. Просрочка записи графика — с 8-го дня, еженедельно
   (``staff_reminders.overdue_weekly``), менеджерам и лифтёрам.
3. Договор обслуживания лифта — стадии до срока, после истечения еженедельно;
   менеджерам.
4. Освидетельствование лифта (``cert_valid_until``) — как договор; менеджерам.
5. Длительный простой — порог по статусу из ``downtime_threshold_days``,
   еженедельно; менеджерам.

Лифтёры — исполнители со специализацией ``elevator`` (алиас ``maintenance``
резолвит ``parse_specializations``); ``universal`` сюда не входит. Адресаты
дедуплицируются по telegram_id (менеджер-лифтёр получает одно сообщение).
Все даты — бизнес-дата ``today`` (``business_today``), часы не читаются.
Тексты HTML-безопасны (подпись лифта экранирована) — слать в parse_mode=HTML.
"""

from __future__ import annotations

import html
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from uk_management_bot.database.models.elevator import Elevator, ElevatorMaintenanceOccurrence
from uk_management_bot.database.models.user import User
from uk_management_bot.services.feedback_service import manager_telegram_ids_sync
from uk_management_bot.utils.auth_helpers import legacy_role_filter
from uk_management_bot.utils.business_time import fmt_date
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.specializations import parse_specializations

from ._core import ElevatorValidationError, Message
from ._shared import DEFAULT_LANGUAGE
from .calendar_rules import (
    DEFAULT_REMINDER_STAGES,
    is_overdue,
    next_reminder_stage,
    should_remind_overdue,
)
from .labels import elevator_label, status_label
from .recipients import Recipient
from .reminder_rules import DOWNTIME_STATUSES, downtime_threshold_reached

LIFT_SPECIALIZATION = "elevator"
ACTIVE_USER_STATUS = "approved"
_LOCALE_PREFIX = "elevators.remind."
OCCURRENCE_TARGET = "occurrence"
ELEVATOR_TARGET = "elevator"
# Куда разрешено писать ``apply_reminders_sync`` (защита от случайной правки паспорта)
_TARGETS: Mapping[str, tuple[type, frozenset[str]]] = {
    OCCURRENCE_TARGET: (
        ElevatorMaintenanceOccurrence,
        frozenset({"reminder_stage", "overdue_reminded_at"}),
    ),
    ELEVATOR_TARGET: (
        Elevator,
        frozenset({
            "contract_reminder_stage", "cert_reminder_stage",
            "contract_overdue_reminded_at", "cert_overdue_reminded_at", "downtime_reminded_at",
        }),
    ),
}

# Параметры текста зависят от языка адресата (подпись статуса) → функция от языка
_Params = Callable[[str], Mapping[str, Any]]


@dataclass(frozen=True)
class StageAdvance:
    """Что записать после тика: ``target`` (occurrence/elevator), id строки, поле, значение."""

    target: str
    row_id: int
    field: str
    value: int | datetime


@dataclass(frozen=True)
class RemindersBatch:
    """Результат тика: сообщения персоналу и продвижения стадий (в одной транзакции)."""

    staff_messages: tuple[Message, ...] = ()
    advances: tuple[StageAdvance, ...] = ()


@dataclass(frozen=True)
class _Audience:
    managers: tuple[Recipient, ...]
    staff: tuple[Recipient, ...]  # менеджеры + лифтёры, без дублей по telegram_id


@dataclass(frozen=True)
class _ExpiryRule:
    """Договор / освидетельствование лифта: поля модели и ключи конфига/локали."""

    key: str  # префикс ключей локали: contract_due / contract_expired
    stages_kind: str  # ключ staff_reminders
    until_attr: str
    stage_attr: str
    reminded_attr: str


_EXPIRY_RULES: tuple[_ExpiryRule, ...] = (
    _ExpiryRule("contract", "contract", "contract_until", "contract_reminder_stage",
                "contract_overdue_reminded_at"),
    _ExpiryRule("cert", "certification", "cert_valid_until", "cert_reminder_stage",
                "cert_overdue_reminded_at"),
)


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------

def _aware(value: datetime | None) -> datetime | None:
    """naive из БД (sqlite) трактуется как UTC — канон ``business_time``."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _stages(config: Mapping[str, Any], kind: str) -> Sequence[int]:
    reminders = config.get("staff_reminders") or {}
    return tuple(reminders.get(kind) or DEFAULT_REMINDER_STAGES)


def _overdue_weekly(config: Mapping[str, Any]) -> bool:
    reminders = config.get("staff_reminders") or {}
    return bool(reminders.get("overdue_weekly", True))


def _render(
    key: str, recipients: Sequence[Recipient], elevator: Elevator, params: _Params
) -> tuple[Message, ...]:
    """Одно сообщение на адресата, на его языке; подпись лифта экранирована."""
    return tuple(
        Message(
            telegram_id=recipient.telegram_id,
            text=get_text(
                _LOCALE_PREFIX + key,
                language=recipient.language,
                label=html.escape(elevator_label(elevator, recipient.language)),
                **params(recipient.language),
            ),
        )
        for recipient in recipients
    )


def _date_params(on: date, days: int) -> _Params:
    return lambda _language: {"date": fmt_date(on), "days": days}


# ---------------------------------------------------------------------------
# Адресаты
# ---------------------------------------------------------------------------

def _to_recipients(users: Sequence[User]) -> tuple[Recipient, ...]:
    return tuple(
        Recipient(user_id=u.id, telegram_id=u.telegram_id, language=u.language or DEFAULT_LANGUAGE)
        for u in users
    )


def _active_users_stmt():
    return select(User).where(
        User.deleted_at.is_(None),
        User.status == ACTIVE_USER_STATUS,
        User.bot_blocked_at.is_(None),
        User.telegram_id.is_not(None),
    ).order_by(User.id)


def _load_audience(db: Session) -> _Audience:
    """Менеджеры (по канону ``feedback_service``) и лифтёры; объединение без дублей."""
    manager_ids = set(manager_telegram_ids_sync(db))
    managers: Sequence[User] = ()
    if manager_ids:
        managers = db.execute(
            _active_users_stmt().where(User.telegram_id.in_(manager_ids))
        ).scalars().all()
    executors = db.execute(
        _active_users_stmt().where(legacy_role_filter("executor"))
    ).scalars().all()
    technicians = [u for u in executors if LIFT_SPECIALIZATION in parse_specializations(u)]
    seen = {u.telegram_id for u in managers}
    extra = [u for u in technicians if u.telegram_id not in seen]
    return _Audience(managers=_to_recipients(managers), staff=_to_recipients([*managers, *extra]))


# ---------------------------------------------------------------------------
# Сбор: график ТО / освидетельствований
# ---------------------------------------------------------------------------

def _planned_occurrences(db: Session, horizon: date) -> Sequence[ElevatorMaintenanceOccurrence]:
    stmt = (
        select(ElevatorMaintenanceOccurrence)
        .join(Elevator, ElevatorMaintenanceOccurrence.elevator_id == Elevator.id)
        .options(
            selectinload(ElevatorMaintenanceOccurrence.elevator).selectinload(Elevator.building)
        )
        .where(
            ElevatorMaintenanceOccurrence.state == "planned",
            ElevatorMaintenanceOccurrence.due_on <= horizon,
            Elevator.archived_at.is_(None),
        )
        .order_by(ElevatorMaintenanceOccurrence.due_on, ElevatorMaintenanceOccurrence.id)
    )
    return db.execute(stmt).scalars().all()


def _occurrence_reminder(
    occ: ElevatorMaintenanceOccurrence, *, today: date, now: datetime,
    config: Mapping[str, Any], audience: _Audience,
) -> tuple[tuple[Message, ...], StageAdvance | None]:
    if occ.due_on >= today:
        stage = next_reminder_stage(occ.due_on, today, occ.reminder_stage or 0, _stages(config, occ.kind))
        if stage is None:
            return (), None
        days = (occ.due_on - today).days
        messages = _render(f"{occ.kind}_due", audience.staff, occ.elevator, _date_params(occ.due_on, days))
        return messages, StageAdvance(OCCURRENCE_TARGET, occ.id, "reminder_stage", stage)
    if not _overdue_weekly(config) or not is_overdue(occ.due_on, today):
        return (), None
    if not should_remind_overdue(_aware(occ.overdue_reminded_at), now):
        return (), None
    days = (today - occ.due_on).days
    messages = _render(f"{occ.kind}_overdue", audience.staff, occ.elevator, _date_params(occ.due_on, days))
    return messages, StageAdvance(OCCURRENCE_TARGET, occ.id, "overdue_reminded_at", now)


# ---------------------------------------------------------------------------
# Сбор: договор / освидетельствование лифта, простой
# ---------------------------------------------------------------------------

def _commissioned_elevators(db: Session) -> Sequence[Elevator]:
    stmt = (
        select(Elevator)
        .options(selectinload(Elevator.building))
        .where(Elevator.archived_at.is_(None), Elevator.is_commissioned.is_(True))
        .order_by(Elevator.id)
    )
    return db.execute(stmt).scalars().all()


def _expiry_reminder(
    elevator: Elevator, rule: _ExpiryRule, *, today: date, now: datetime,
    config: Mapping[str, Any], managers: Sequence[Recipient],
) -> tuple[tuple[Message, ...], StageAdvance | None]:
    until: date | None = getattr(elevator, rule.until_attr)
    if until is None:
        return (), None
    if today <= until:
        last_stage = getattr(elevator, rule.stage_attr) or 0
        stage = next_reminder_stage(until, today, last_stage, _stages(config, rule.stages_kind))
        if stage is None:
            return (), None
        messages = _render(f"{rule.key}_due", managers, elevator, _date_params(until, (until - today).days))
        return messages, StageAdvance(ELEVATOR_TARGET, elevator.id, rule.stage_attr, stage)
    if not _overdue_weekly(config):
        return (), None
    if not should_remind_overdue(_aware(getattr(elevator, rule.reminded_attr)), now):
        return (), None
    messages = _render(f"{rule.key}_expired", managers, elevator, _date_params(until, (today - until).days))
    return messages, StageAdvance(ELEVATOR_TARGET, elevator.id, rule.reminded_attr, now)


def _downtime_reminder(
    elevator: Elevator, *, now: datetime, config: Mapping[str, Any], managers: Sequence[Recipient],
) -> tuple[tuple[Message, ...], StageAdvance | None]:
    status = elevator.current_status
    since = _aware(elevator.status_since)
    if status not in DOWNTIME_STATUSES or since is None:
        return (), None
    thresholds = config.get("downtime_threshold_days") or {}
    if not downtime_threshold_reached(status, since, now, thresholds):
        return (), None
    if not should_remind_overdue(_aware(elevator.downtime_reminded_at), now):
        return (), None
    days = (now - since).days

    def params(language: str) -> Mapping[str, Any]:
        return {"status": status_label(status, language), "date": fmt_date(since), "days": days}

    return (
        _render("downtime", managers, elevator, params),
        StageAdvance(ELEVATOR_TARGET, elevator.id, "downtime_reminded_at", now),
    )


# ---------------------------------------------------------------------------
# Публичный контракт
# ---------------------------------------------------------------------------

def collect_reminders_sync(
    db: Session, *, now: datetime, today: date, config: Mapping[str, Any]
) -> RemindersBatch:
    """Собрать напоминания тика: сообщения персоналу + продвижения стадий. БД не пишет.

    ``now`` — tz-aware UTC-инстант тика, ``today`` — его бизнес-дата
    (``business_today(now)``), ``config`` — полный конфиг модуля (``load_config_sync``).
    """
    audience = _load_audience(db)
    horizon = today + timedelta(days=max(
        max(_stages(config, "maintenance")), max(_stages(config, "certification")),
    ))
    results: list[tuple[tuple[Message, ...], StageAdvance | None]] = [
        _occurrence_reminder(occ, today=today, now=now, config=config, audience=audience)
        for occ in _planned_occurrences(db, horizon)
    ]
    for elevator in _commissioned_elevators(db):
        results.extend(
            _expiry_reminder(elevator, rule, today=today, now=now, config=config,
                             managers=audience.managers)
            for rule in _EXPIRY_RULES
        )
        results.append(_downtime_reminder(elevator, now=now, config=config, managers=audience.managers))
    return RemindersBatch(
        staff_messages=tuple(message for messages, _ in results for message in messages),
        advances=tuple(advance for _, advance in results if advance is not None),
    )


def apply_reminders_sync(db: Session, batch: RemindersBatch) -> int:
    """Записать продвижения стадий (flush, без commit); вернуть число применённых.

    Пишутся только поля напоминаний (``_TARGETS``), иное → ``ElevatorValidationError``.
    Исчезнувшая строка пропускается. ``version`` лифта не трогается: метки
    напоминаний — не правка паспорта, менеджер не должен ловить конфликт версий.
    """
    applied = 0
    for advance in batch.advances:
        if advance.target not in _TARGETS:
            raise ElevatorValidationError(f"неизвестная цель напоминания {advance.target!r}")
        model, fields = _TARGETS[advance.target]
        if advance.field not in fields:
            raise ElevatorValidationError(f"поле {advance.field!r} не является полем напоминаний")
        row = db.get(model, advance.row_id)
        if row is None:
            continue
        setattr(row, advance.field, advance.value)
        applied += 1
    db.flush()
    return applied
