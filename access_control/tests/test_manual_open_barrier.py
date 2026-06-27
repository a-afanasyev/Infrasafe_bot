"""Ф5: самостоятельное ручное открытие barriers/{id}/manual-open (§9.5, §13.2).

Покрывает критерий приёмки §15.8: прямой manual-open при активном pending_review
возвращает конфликт + event_id и НЕ создаёт команду. Также — happy-path (нет
pending → команда создаётся) и lazy-expiry (просроченный pending не блокирует).
PostgreSQL-only (advisory lock §13.2).
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import text

from access_control.services.lifecycle import (
    PendingReviewConflict,
    manual_open_barrier,
)
from access_control.tests.conftest import (
    PilotFixture,
    seed_pending_review,
    seed_user,
    utcnow,
)


def _commands_for_barrier(db, barrier_id: int) -> int:
    return db.execute(
        text("SELECT count(*) FROM barrier_commands WHERE barrier_id = :b"),
        {"b": barrier_id},
    ).scalar()


def test_standalone_open_without_pending_creates_command(
    pg_db, pilot: PilotFixture
) -> None:
    """Нет pending → manual_openings (decision_id NULL) + команда + audit."""
    op = seed_user(pg_db, roles="security_operator")
    result = manual_open_barrier(
        pg_db,
        barrier_id=pilot.barrier_id,
        operator_user_id=op,
        reason="аварийное открытие",
        source="emergency",
    )
    assert result.command_id is not None
    assert _commands_for_barrier(pg_db, pilot.barrier_id) == 1
    # manual_openings создан с decision_id NULL (самостоятельная операция).
    row = pg_db.execute(
        text(
            "SELECT operator_user_id, reason, decision_id, command_id "
            "FROM manual_openings WHERE id = :id"
        ),
        {"id": result.manual_opening_id},
    ).first()
    assert row[0] == op
    assert row[1] == "аварийное открытие"
    assert row[2] is None
    assert str(row[3]) == result.command_id


def test_standalone_open_with_active_pending_conflict(
    pg_db, pilot: PilotFixture
) -> None:
    """Критерий 8: активный pending_review → конфликт + event_id, без команды."""
    op = seed_user(pg_db, roles="security_operator")
    pending = seed_pending_review(pg_db, pilot)

    with pytest.raises(PendingReviewConflict) as exc:
        manual_open_barrier(
            pg_db,
            barrier_id=pilot.barrier_id,
            operator_user_id=op,
            reason="попытка обойти review",
            source="emergency",
        )
    assert exc.value.event_id == pending.camera_event_id
    # Команда НЕ создана.
    assert _commands_for_barrier(pg_db, pilot.barrier_id) == 0


def test_standalone_open_with_expired_pending_proceeds(
    pg_db, pilot: PilotFixture
) -> None:
    """Просроченный pending (lazy-expiry) не блокирует самостоятельный manual-open."""
    op = seed_user(pg_db, roles="security_operator")
    seed_pending_review(
        pg_db, pilot, deadline_at=utcnow() - dt.timedelta(seconds=5)
    )

    result = manual_open_barrier(
        pg_db,
        barrier_id=pilot.barrier_id,
        operator_user_id=op,
        reason="после просрочки",
        source="emergency",
    )
    assert result.command_id is not None
    assert _commands_for_barrier(pg_db, pilot.barrier_id) == 1
