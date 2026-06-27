"""Доступ к ``manual_openings`` (append-only, §9.5/§9.7).

Проверка недавнего ручного открытия и append-запись с hash-chain.
Транзакция/lock — в сервисе.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from access_control.domain.audit import ManualOpening
from access_control.services.hashchain import next_hash


def recent_open_exists(
    db: Session, *, barrier_id: int, since: dt.datetime
) -> bool:
    """Создана ли ручная команда (manual_opening) для barrier ПОСЛЕ ``since`` (§13.2).

    Под per-barrier lock ingestion: если оператор уже открыл шлагбаум вручную после
    момента события, решение фиксируется allowed_manually, новый pending не создаётся.
    """
    return (
        db.execute(
            text(
                "SELECT 1 FROM manual_openings "
                "WHERE barrier_id = :b AND created_at >= :ts LIMIT 1"
            ),
            {"b": barrier_id, "ts": since},
        ).scalar()
        is not None
    )


def insert(
    db: Session,
    *,
    barrier_id: int,
    command_id: str,
    decision_id: int | None,
    operator_user_id: int,
    reason: str,
    captured_event_id: int | None,
) -> int:
    """Append-строка manual_openings с hash-chain (§9.5, §9.7). Возвращает id строки."""
    payload = {
        "barrier_id": barrier_id,
        "command_id": command_id,
        "decision_id": decision_id,
        "operator_user_id": operator_user_id,
        "reason": reason,
        "captured_event_id": captured_event_id,
    }
    prev_hash, row_hash = next_hash(db, "manual_openings", payload)
    row = ManualOpening(
        barrier_id=barrier_id,
        command_id=uuid.UUID(command_id),
        decision_id=decision_id,
        operator_user_id=operator_user_id,
        reason=reason,
        captured_event_id=captured_event_id,
        prev_hash=prev_hash,
        row_hash=row_hash,
    )
    db.add(row)
    db.flush()
    return row.id
