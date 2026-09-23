"""Старт/стоп смены исполнителем — единое правило для бота и TWA-API (A9-P1-2).

Раньше правило жило только в боте (`ShiftService.start_shift`): «расписание —
источник истины» (решение владельца 2026-08-24) — если у сотрудника есть
ЗАПЛАНИРОВАННАЯ смена, чьё окно уже идёт, старт активирует ЕЁ, ad-hoc — только
когда такой нет. TWA (`api/shifts/executor_router.py`) всегда создавал ad-hoc
→ две смены на одно окно; start/end из TWA не писали AuditLog и не слали
уведомлений.

Канон как у `utils/shifts.py` / `workflow_runner`: одно правило
(`_running_planned_filter`, `_apply_start`, `_apply_end`, `_audit`) и две
тонкие обёртки sync/async, расходится только ORM-I/O. Обёртки НЕ коммитят:
смена и её audit — одна транзакция, коммитит вызывающий. Уведомление —
payload (`shift_notify_payload`), отправка — после коммита, вне db-фазы.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.services.notification_service.channel import (
    send_to_channel,
    send_to_user,
)
from uk_management_bot.services.notification_service.shifts import (
    build_shift_ended_message,
    build_shift_started_message,
)
from uk_management_bot.utils.constants import (
    AUDIT_ACTION_SHIFT_ENDED,
    AUDIT_ACTION_SHIFT_STARTED,
    SHIFT_STATUS_ACTIVE,
    SHIFT_STATUS_COMPLETED,
)
from uk_management_bot.utils.datetime_utils import utc_now

SHIFT_STATUS_PLANNED = "planned"

# (telegram_id исполнителя, текст исполнителю, текст в ops-канал)
ShiftNotify = tuple[int, str, str]


# ==========================================================================
# Правило (общее для sync и async)
# ==========================================================================

def _running_planned_filter(user_id: int, now: datetime):
    """Запланированная смена сотрудника, чьё окно уже идёт в момент `now`."""
    return (
        (Shift.user_id == user_id)
        & (Shift.status == SHIFT_STATUS_PLANNED)
        & (Shift.start_time <= now)
        & (Shift.end_time > now)
    )


def _append_notes(current: Optional[str], notes: Optional[str]) -> Optional[str]:
    if not notes:
        return current
    return f"{current}\n{notes}" if current else notes  # html-raw: пишется в shift.notes


def _apply_start(planned: Optional[Shift], *, user_id: int, now: datetime,
                 notes: Optional[str]) -> tuple[Shift, bool]:
    """-> (смена, создана_ли_новая). Идущая planned активируется, иначе ad-hoc."""
    if planned is not None:
        planned.status = SHIFT_STATUS_ACTIVE
        planned.notes = _append_notes(planned.notes, notes)
        return planned, False
    return Shift(user_id=user_id, start_time=now, status=SHIFT_STATUS_ACTIVE, notes=notes), True


def _apply_end(shift: Shift, *, now: datetime, notes: Optional[str]) -> None:
    shift.end_time = now
    shift.status = SHIFT_STATUS_COMPLETED
    shift.notes = _append_notes(shift.notes, notes)


def _audit(user: User, action: str, details: dict) -> AuditLog:
    return AuditLog(
        user_id=user.id,
        telegram_user_id=user.telegram_id,
        action=action,
        details=details,
    )


def _start_audit(user: User, shift: Shift, notes: Optional[str]) -> AuditLog:
    return _audit(user, AUDIT_ACTION_SHIFT_STARTED, {"shift_id": shift.id, "notes": notes})


def _end_audit(user: User, shift: Shift, notes: Optional[str]) -> AuditLog:
    return _audit(user, AUDIT_ACTION_SHIFT_ENDED, {
        "shift_id": shift.id,
        "notes": notes,
        "specializations": shift.specialization_focus,
    })


# ==========================================================================
# Обёртки: sync (бот, run_db-поток) / async (API). Без commit.
# ==========================================================================

def start_shift_sync(db: Session, user: User, notes: Optional[str] = None) -> Shift:
    now = utc_now()
    # FOR UPDATE: двойной тап / бот+TWA одновременно — второй ждёт commit
    # первого и уже не видит planned. На sqlite — no-op.
    planned = (
        db.query(Shift)
        .filter(_running_planned_filter(user.id, now))
        .order_by(Shift.start_time)
        .with_for_update()
        .first()
    )
    shift, created = _apply_start(planned, user_id=user.id, now=now, notes=notes)
    if created:
        db.add(shift)
    db.flush()  # shift.id для audit
    db.add(_start_audit(user, shift, notes))
    return shift


def start_planned_shift_sync(db: Session, user: User, shift_id: int,
                             notes: Optional[str] = None) -> Optional[Shift]:
    """«Мои смены → Начать» (A9-P2-32): активировать КОНКРЕТНУЮ planned-смену.

    Смена выбрана явно по id, окно не проверяется (как и раньше в «Моих
    сменах»); владелец и статус — в SQL-фильтре. Плановый start_time
    сохраняется, audit — как у `start_shift_sync`. None — смены нет, чужая
    или уже не planned (без audit). Без commit.
    """
    # FOR UPDATE: двойной тап — второй ждёт commit первого и видит status != planned.
    shift = (
        db.query(Shift)
        .filter(
            (Shift.id == shift_id)
            & (Shift.user_id == user.id)
            & (Shift.status == SHIFT_STATUS_PLANNED)
        )
        .with_for_update()
        .first()
    )
    if shift is None:
        return None
    _apply_start(shift, user_id=user.id, now=utc_now(), notes=notes)
    db.add(_start_audit(user, shift, notes))
    return shift


async def start_shift_async(db: AsyncSession, user: User, notes: Optional[str] = None) -> Shift:
    now = utc_now()
    planned = (
        await db.execute(
            select(Shift)
            .where(_running_planned_filter(user.id, now))
            .order_by(Shift.start_time)
            .limit(1)
            .with_for_update()
        )
    ).scalars().first()
    shift, created = _apply_start(planned, user_id=user.id, now=now, notes=notes)
    if created:
        db.add(shift)
    await db.flush()
    db.add(_start_audit(user, shift, notes))
    return shift


def end_shift_sync(db: Session, user: User, shift: Shift, notes: Optional[str] = None) -> Shift:
    """`shift` — уже проверенная вызывающим активная смена `user`."""
    _apply_end(shift, now=utc_now(), notes=notes)
    db.add(_end_audit(user, shift, notes))
    return shift


async def end_shift_async(db: AsyncSession, user: User, shift: Shift,
                          notes: Optional[str] = None) -> Shift:
    """async-зеркало `end_shift_sync` (I/O нет: сессия нужна для add)."""
    _apply_end(shift, now=utc_now(), notes=notes)
    db.add(_end_audit(user, shift, notes))
    return shift


# ==========================================================================
# Уведомление: те же тексты и адресаты, что у бота (исполнитель + ops-канал)
# ==========================================================================

def shift_notify_payload(user: User, shift: Shift, *, started: bool) -> Optional[ShiftNotify]:
    if not user.telegram_id:
        return None
    build = build_shift_started_message if started else build_shift_ended_message
    return (
        user.telegram_id,
        build(user, shift, for_channel=False),
        build(user, shift, for_channel=True),
    )


async def send_shift_notify(bot, payload: Optional[ShiftNotify]) -> None:
    """Best-effort: send_to_user/send_to_channel сами логируют и глотают сбой."""
    if not payload:
        return
    user_tg, user_text, channel_text = payload
    await send_to_user(bot, user_tg, user_text)
    await send_to_channel(bot, channel_text)
