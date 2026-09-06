"""Смена статуса лифта из бота — один sync-юнит для двух поверхностей.

Подсказка менеджеру после подтверждения заявки (``admin/elevator_hint.py``,
``source="request_hint"``) и меню лифтёра (``elevators/_units.py``,
``source="manual"``) делают одно и то же: ``set_status_sync`` → commit →
вернуть сообщения жителям вызывающему (отправка — ПОСЛЕ commit, у него).
Авторизацию (роль / специализация / принадлежность номера заявки лифту)
проверяет вызывающий ДО этого юнита; здесь — только доменная операция.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from uk_management_bot.services.elevator_service import (
    ElevatorConflictError,
    ElevatorNotFoundError,
    ElevatorValidationError,
    load_config_sync,
    set_status_sync,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StatusOutcome:
    """Итог смены статуса; ``verdict`` — changed | unchanged | not_found | rejected
    (вызывающий может добавлять свои вердикты доступа)."""

    verdict: str
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    messages: tuple[tuple[int, str], ...] = ()


def apply_elevator_status(
    db: Session, elevator_id: int, status: str, *, actor_user_id: Optional[int], source: str,
    reason: Optional[str] = None, request_number: Optional[str] = None,
) -> StatusOutcome:
    """``set_status_sync`` + commit; идемпотентный повтор — ``unchanged`` без записи."""
    try:
        change = set_status_sync(
            db, elevator_id, status, actor_user_id=actor_user_id, source=source,
            reason=reason, request_number=request_number, config=load_config_sync(db),
        )
    except ElevatorNotFoundError:
        return StatusOutcome("not_found")
    except (ElevatorConflictError, ElevatorValidationError) as exc:
        db.rollback()
        logger.info("Статус лифта %s (%s) отклонён: %s", elevator_id, source, exc)
        return StatusOutcome("rejected")
    if not change.changed:
        return StatusOutcome("unchanged", change.old_status, change.new_status)
    db.commit()
    return StatusOutcome(
        "changed", change.old_status, change.new_status,
        tuple((m.telegram_id, m.text) for m in change.resident_messages),
    )
