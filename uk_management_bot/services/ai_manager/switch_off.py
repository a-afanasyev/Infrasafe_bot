"""Выключение режима ИИ (ai → rule): предупредить менеджеров об эскалациях.

Лестница SLA не хранит очередей — состояние выводится из audit_logs, и
при выключении ничего не «висит». Но заявки, по которым ИИ уже пинговал
людей, остаются открытыми без дальнейшего надзора — менеджер получает одно
сообщение с их числом. Чистые sync-функции; отправку делает вызывающий.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.request import Request
from uk_management_bot.services.ai_manager.sla import AUDIT_STEP
from uk_management_bot.utils.datetime_utils import utc_now
from uk_management_bot.utils.workflow_predicates import active_status_clause

_WINDOW = timedelta(days=30)


def count_escalating_sync(db: Session) -> int:
    """Открытые заявки с хотя бы одним шагом лестницы за 30 дней."""
    numbers = {
        details.get("request_number")
        for details in db.execute(
            select(AuditLog.details)
            .where(AuditLog.action == AUDIT_STEP)
            .where(AuditLog.created_at >= utc_now() - _WINDOW)
        ).scalars()
        if details
    }
    numbers.discard(None)
    if not numbers:
        return 0
    open_numbers = db.execute(
        select(Request.request_number)
        .where(Request.request_number.in_(sorted(numbers)))
        .where(active_status_clause())
    ).scalars().all()
    return len(open_numbers)


def manager_notices_sync(db: Session, old_mode: str, new_mode: str) -> list[tuple[int, str]]:
    """(telegram_id, text) менеджерам при переходе ai → не-ai; иначе пусто."""
    if old_mode != "ai" or new_mode == "ai":
        return []
    count = count_escalating_sync(db)
    if count == 0:
        return []
    from uk_management_bot.services.ai_manager.channels import resolve_managers
    from uk_management_bot.utils.helpers import get_text

    text = get_text("ai_manager.switched_off", language="ru", count=count)
    return [(tg_id, text) for tg_id in resolve_managers(db)]
