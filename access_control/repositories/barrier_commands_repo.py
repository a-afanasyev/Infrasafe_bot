"""Доступ к ``barrier_commands`` (durable outbox команд открытия, §9.2).

Идемпотентное создание команды по ``UNIQUE(decision_id)`` и чтение команды
решения. Транзакция/lock — в сервисе.
"""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from access_control.domain.commands import BarrierCommand
from access_control.domain.enums import CommandStatus, CommandType


@dataclass(frozen=True)
class CommandRow:
    """Нейтральная ссылка на созданную/существующую команду открытия."""

    command_id: str
    barrier_id: int
    expires_at: dt.datetime | None


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def command_for_decision(db: Session, decision_id: int) -> BarrierCommand | None:
    """Команда открытия, привязанная к решению (или ``None``)."""
    return (
        db.query(BarrierCommand)
        .filter(BarrierCommand.decision_id == decision_id)
        .first()
    )


def create_open_command(
    db: Session,
    *,
    controller_id: int,
    barrier_id: int,
    decision_id: int | None,
    ttl_seconds: int,
) -> CommandRow:
    """Создать команду открытия в durable outbox (§9.2).

    ``decision_id`` задан — идемпотентно по ``UNIQUE(decision_id)`` (ON CONFLICT DO
    NOTHING, при конфликте возвращается уже сохранённая команда); ``decision_id``
    NULL (самостоятельный manual-open) — каждая операция = новая команда (нет
    ключа идемпотентности, ручные открытия независимы).
    """
    expires_at = _utcnow() + dt.timedelta(seconds=ttl_seconds)
    new_command_id = uuid.uuid4()
    base = pg_insert(BarrierCommand.__table__).values(
        command_id=new_command_id,
        decision_id=decision_id,
        controller_id=controller_id,
        barrier_id=barrier_id,
        command_type=CommandType.OPEN_BARRIER.value,
        status=CommandStatus.PENDING.value,
        expires_at=expires_at,
    )
    if decision_id is not None:
        stmt = base.on_conflict_do_nothing(
            index_elements=["decision_id"],
            index_where=text("decision_id IS NOT NULL"),
        ).returning(BarrierCommand.__table__.c.command_id)
        inserted = db.execute(stmt).scalar()
        if inserted is None:
            # Команда на это решение уже существует — вернуть сохранённую (idempotent).
            existing = command_for_decision(db, decision_id)
            return CommandRow(
                command_id=str(existing.command_id),
                barrier_id=existing.barrier_id,
                expires_at=existing.expires_at,
            )
        return CommandRow(str(new_command_id), barrier_id, expires_at)
    db.execute(base)
    return CommandRow(str(new_command_id), barrier_id, expires_at)
