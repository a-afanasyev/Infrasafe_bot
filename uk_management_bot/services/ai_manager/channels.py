"""Каналы доставки ИИ-менеджера: куда и как слать пинги лестницы.

Единственная точка «адресат → отправка»: DM человеку, staff-группа
исполнителей, менеджеры, группа жителей. Адресаты резолвятся в DB-фазе
(``resolve_*`` — sync, с сессией), отправка — после неё (``deliver`` —
async, без БД). Будущие ступени (SMS, звонок) добавляются как новый ``kind``
здесь, лестница их не знает.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from uk_management_bot.database.models.monitored_group import (
    GROUP_KIND_RESIDENTS,
    GROUP_KIND_STAFF,
    MonitoredGroup,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Outgoing:
    """Готовое к отправке сообщение: Telegram chat_id (человек или группа)."""
    chat_id: int
    text: str
    kind: str  # dm | staff_group | manager | residents_group — только для логов


def resolve_staff_group(db: Session) -> Optional[int]:
    """chat_id активной staff-группы (первая по id), иначе None."""
    row = db.execute(
        select(MonitoredGroup.chat_id)
        .where(MonitoredGroup.kind == GROUP_KIND_STAFF, MonitoredGroup.is_active.is_(True))
        .order_by(MonitoredGroup.id).limit(1)
    ).first()
    return int(row[0]) if row else None


def resolve_residents_group(db: Session, chat_id: int) -> Optional[int]:
    """Тот же chat_id, если это активная группа жителей (заявка из Group Intake)."""
    row = db.execute(
        select(MonitoredGroup.chat_id)
        .where(MonitoredGroup.chat_id == chat_id,
               MonitoredGroup.kind == GROUP_KIND_RESIDENTS,
               MonitoredGroup.is_active.is_(True))
        .limit(1)
    ).first()
    return int(row[0]) if row else None


def resolve_managers(db: Session) -> list[int]:
    """Telegram-id менеджеров — та же аудитория, что у send_manager_notification."""
    from uk_management_bot.services.feedback_service import manager_telegram_ids_sync

    return list(manager_telegram_ids_sync(db))


async def deliver(bot, message: Outgoing) -> bool:
    """Отправка без БД; сбой логируется, не бросается (BUG-BOT-036)."""
    from uk_management_bot.services.notification_service.channel import send_to_user

    ok = await send_to_user(bot, message.chat_id, message.text)
    if not ok:
        logger.warning("ai_manager.channels: %s to %s not delivered", message.kind, message.chat_id)
    return ok
