"""Ф5: review-expiry worker + lazy expiry (§9.5). PostgreSQL-only.

Покрывает критерий приёмки §15.9 (часть):
* (c) worker переводит просроченный pending в expired новым переходом, без команды;
* (d) lazy expiry: попытка resolve просроченного pending → expired, без команды;
* идемпотентность worker (повтор не создаёт второй переход).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import text

from access_control.services.lifecycle import resolve_event
from access_control.services.review_expiry import expire_due_reviews
from access_control.tests.conftest import (
    PilotFixture,
    seed_pending_review,
    seed_user,
    utcnow,
)


def _tip_status(db, camera_event_id: int) -> str:
    return db.execute(
        text(
            "SELECT status FROM access_decisions WHERE camera_event_id = :e "
            "AND NOT EXISTS (SELECT 1 FROM access_decisions c "
            "                WHERE c.supersedes_decision_id = access_decisions.id) "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"e": camera_event_id},
    ).scalar()


def _count_decisions(db, camera_event_id: int) -> int:
    return db.execute(
        text("SELECT count(*) FROM access_decisions WHERE camera_event_id = :e"),
        {"e": camera_event_id},
    ).scalar()


def _commands_for_barrier(db, barrier_id: int) -> int:
    return db.execute(
        text("SELECT count(*) FROM barrier_commands WHERE barrier_id = :b"),
        {"b": barrier_id},
    ).scalar()


def test_worker_expires_due_pending(pg_db, pilot: PilotFixture) -> None:
    """Критерий 9(c): worker → expired новым переходом, без команды."""
    pending = seed_pending_review(
        pg_db, pilot, deadline_at=utcnow() - dt.timedelta(seconds=1)
    )
    n = expire_due_reviews(pg_db)
    assert n == 1
    assert _tip_status(pg_db, pending.camera_event_id) == "expired"
    assert _count_decisions(pg_db, pending.camera_event_id) == 2
    assert _commands_for_barrier(pg_db, pilot.barrier_id) == 0


def test_worker_does_not_expire_fresh_pending(pg_db, pilot: PilotFixture) -> None:
    """Свежий pending (deadline в будущем) не трогается worker'ом."""
    pending = seed_pending_review(
        pg_db, pilot, deadline_at=utcnow() + dt.timedelta(seconds=120)
    )
    assert expire_due_reviews(pg_db) == 0
    assert _tip_status(pg_db, pending.camera_event_id) == "pending_review"


def test_worker_idempotent_no_double(pg_db, pilot: PilotFixture) -> None:
    """Повторный tick не создаёт второй expired-переход (идемпотентность)."""
    pending = seed_pending_review(
        pg_db, pilot, deadline_at=utcnow() - dt.timedelta(seconds=1)
    )
    assert expire_due_reviews(pg_db) == 1
    assert expire_due_reviews(pg_db) == 0
    assert _count_decisions(pg_db, pending.camera_event_id) == 2


def test_lazy_expiry_on_resolve(pg_db, pilot: PilotFixture) -> None:
    """Критерий 9(d): resolve просроченного pending → expired, без команды."""
    op = seed_user(pg_db, roles="security_operator")
    pending = seed_pending_review(
        pg_db, pilot, deadline_at=utcnow() - dt.timedelta(seconds=1)
    )

    result = resolve_event(
        pg_db,
        event_id=pending.camera_event_id,
        action="manual_open",
        operator_user_id=op,
        reason="опоздал",
        barrier_id=pilot.barrier_id,
        decision_id=pending.decision_id,
        source="operator_resolve",
    )
    assert result.status == "expired"
    assert result.command_id is None
    assert _commands_for_barrier(pg_db, pilot.barrier_id) == 0

    # Повторная попытка резолюции возвращает сохранённый expired без новой команды.
    again = resolve_event(
        pg_db,
        event_id=pending.camera_event_id,
        action="manual_open",
        operator_user_id=op,
        reason="ещё раз",
        barrier_id=pilot.barrier_id,
        decision_id=pending.decision_id,
        source="operator_resolve",
    )
    assert again.status == "expired"
    assert again.replayed is True
    assert _count_decisions(pg_db, pending.camera_event_id) == 2
    assert _commands_for_barrier(pg_db, pilot.barrier_id) == 0


def _audit_count(db, action: str) -> int:
    return db.execute(
        text("SELECT count(*) FROM access_audit_logs WHERE action = :a"),
        {"a": action},
    ).scalar()


def test_worker_expires_pending_with_deactivated_barrier(
    pg_db, pilot: PilotFixture
) -> None:
    """M4: barrier деактивирован — просроченный pending всё равно истекает (не вечный).

    Lock-ключ падает на gate_id (LEFT JOIN на активный barrier), worker находит и
    переводит pending в expired.
    """
    pending = seed_pending_review(
        pg_db, pilot, deadline_at=utcnow() - dt.timedelta(seconds=1)
    )
    pg_db.execute(
        text("UPDATE access_barriers SET is_active = false WHERE id = :b"),
        {"b": pilot.barrier_id},
    )
    pg_db.commit()
    n = expire_due_reviews(pg_db)
    assert n == 1
    assert _tip_status(pg_db, pending.camera_event_id) == "expired"


def test_worker_writes_audit_on_expiry(pg_db, pilot: PilotFixture) -> None:
    """L5: каждый переход в expired worker'ом пишет audit (actor=None, system)."""
    seed_pending_review(
        pg_db, pilot, deadline_at=utcnow() - dt.timedelta(seconds=1)
    )
    assert _audit_count(pg_db, "access.review_expired") == 0
    expire_due_reviews(pg_db)
    assert _audit_count(pg_db, "access.review_expired") == 1
    row = pg_db.execute(
        text(
            "SELECT actor_user_id, details FROM access_audit_logs "
            "WHERE action = 'access.review_expired'"
        )
    ).first()
    assert row[0] is None  # system actor
    assert row[1]["source"] == "review_expiry_worker"


def test_lazy_expiry_audit_actor_is_system(pg_db, pilot: PilotFixture) -> None:
    """L4: lazy-expiry — actor=None (system), инициатор в details.triggered_by_user_id."""
    op = seed_user(pg_db, roles="security_operator")
    pending = seed_pending_review(
        pg_db, pilot, deadline_at=utcnow() - dt.timedelta(seconds=1)
    )
    resolve_event(
        pg_db,
        event_id=pending.camera_event_id,
        action="deny",
        operator_user_id=op,
        reason="поздно",
        barrier_id=pilot.barrier_id,
        decision_id=pending.decision_id,
        source="operator_resolve",
    )
    row = pg_db.execute(
        text(
            "SELECT actor_user_id, details FROM access_audit_logs "
            "WHERE action = 'access.review_expired_lazy'"
        )
    ).first()
    assert row is not None
    assert row[0] is None  # actor = system, не оператор
    assert row[1]["triggered_by_user_id"] == op
