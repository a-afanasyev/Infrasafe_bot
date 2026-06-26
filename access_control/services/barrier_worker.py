"""Worker durable-очереди barrier_commands (§9.2). ОТДЕЛЬНЫЙ от webhook_outbox.

Обслуживает таблицу ``barrier_commands`` (НЕ ``webhook_outbox`` — §15.11):

* ``reclaim_expired_leases`` — протухший lease с ``attempts < max_attempts``
  возвращается в ``pending`` (повторная доставка);
* ``mark_dead_letters`` — протухший lease с ``attempts >= max_attempts`` →
  ``dead`` (retry/dead-letter policy); ``dead`` не лизится и не исполняется;
* ``queue_metrics`` — возраст очереди и счётчики по контроллеру (наблюдаемость);
* ``tick`` — один детерминированный проход (dead-letter затем reclaim), чтобы
  гонять в тесте без бесконечного цикла. Прод-обёртка-runner — опциональна.

ВАЖНО (§9.2, долг Ф2): все ``UPDATE`` по ``barrier_commands`` проставляют
``updated_at = now()`` явно — ORM ``onupdate`` не срабатывает на raw SQL.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

DEFAULT_DEAD_LETTER_ERROR = "lease expired after max_attempts (dead-letter)"


@dataclass(frozen=True)
class TickResult:
    """Итог одного прохода worker'а."""

    reclaimed: int
    dead: int


@dataclass(frozen=True)
class QueueMetrics:
    """Метрики очереди по контроллеру (§9.2, возраст очереди + счётчики)."""

    controller_id: int
    max_pending_age_seconds: float | None
    pending: int
    leased: int
    dead: int


def reclaim_expired_leases(db: Session) -> int:
    """Вернуть в pending протухшие lease с attempts < max_attempts. Возвращает число."""
    result = db.execute(
        text(
            """
            UPDATE barrier_commands
            SET status = 'pending',
                lease_token = NULL,
                lease_expires_at = NULL,
                updated_at = now()
            WHERE status = 'leased'
              AND lease_expires_at < now()
              AND attempts < max_attempts
            """
        )
    )
    return result.rowcount


def mark_dead_letters(db: Session, *, error: str = DEFAULT_DEAD_LETTER_ERROR) -> int:
    """Перевести в dead протухшие lease с attempts >= max_attempts. Возвращает число."""
    result = db.execute(
        text(
            """
            UPDATE barrier_commands
            SET status = 'dead',
                dead_at = now(),
                last_error = :err,
                updated_at = now()
            WHERE status = 'leased'
              AND lease_expires_at < now()
              AND attempts >= max_attempts
            """
        ),
        {"err": error},
    )
    return result.rowcount


def tick(db: Session, *, error: str = DEFAULT_DEAD_LETTER_ERROR) -> TickResult:
    """Один детерминированный проход: сначала dead-letter, затем reclaim, commit.

    Порядок важен: протухший lease с исчерпанными попытками должен стать ``dead``,
    а не вернуться в ``pending`` (иначе вечный цикл повторов).
    """
    dead = mark_dead_letters(db, error=error)
    reclaimed = reclaim_expired_leases(db)
    db.commit()
    return TickResult(reclaimed=reclaimed, dead=dead)


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
