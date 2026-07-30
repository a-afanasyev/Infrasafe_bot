"""Метрики durable-очереди barrier_commands (§9.2). ОТДЕЛЬНО от webhook_outbox.

Обслуживает таблицу ``barrier_commands`` (НЕ ``webhook_outbox`` — §15.11):

* ``queue_metrics`` — возраст очереди и счётчики по контроллеру (наблюдаемость).

Worker-функции pull-модели (reclaim_expired_leases / mark_dead_letters / tick)
удалены как мёртвый код (AUD6): прод-runner так и не появился, единственными
потребителями были их собственные тесты.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class QueueMetrics:
    """Метрики очереди по контроллеру (§9.2, возраст очереди + счётчики)."""

    controller_id: int
    max_pending_age_seconds: float | None
    pending: int
    leased: int
    dead: int


def queue_metrics(db: Session, controller_id: int) -> QueueMetrics:
    """Метрики очереди контроллера: max возраст pending + число pending/leased/dead."""
    row = db.execute(
        text(
            """
            SELECT
              EXTRACT(EPOCH FROM (
                  now() - MIN(created_at) FILTER (WHERE status = 'pending')
              )) AS max_pending_age,
              COUNT(*) FILTER (WHERE status = 'pending') AS pending,
              COUNT(*) FILTER (WHERE status = 'leased') AS leased,
              COUNT(*) FILTER (WHERE status = 'dead') AS dead
            FROM barrier_commands
            WHERE controller_id = :cid
            """
        ),
        {"cid": controller_id},
    ).first()
    age = float(row[0]) if row is not None and row[0] is not None else None
    return QueueMetrics(
        controller_id=controller_id,
        max_pending_age_seconds=age,
        pending=int(row[1]) if row else 0,
        leased=int(row[2]) if row else 0,
        dead=int(row[3]) if row else 0,
    )
