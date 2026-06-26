"""Ф5: резолюция manual_review через resolve_event (§9.5, §13.2). PostgreSQL-only.

Покрывает критерии приёмки §15:
* 9(a) resolve manual_open → allowed_manually + команда в barrier_commands;
* 9(b) resolve deny → denied_manually без команды;
* 9(e) повторная резолюция возвращает сохранённый результат, без второй
  команды/перехода (идемпотентность по event/decision);
* 7 (часть): успешный manual_open фиксирует operator_user_id и reason в manual_openings;
* append-only: переходы — НОВЫМИ строками (supersedes), исходный pending не UPDATE.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from access_control.services.lifecycle import (
    BarrierUnavailableError,
    DecisionIdMismatch,
    NoPendingReviewError,
    resolve_event,
)
from access_control.tests.conftest import (
    PilotFixture,
    seed_pending_review,
    seed_user,
)


def _count_decisions(db, camera_event_id: int) -> int:
    return db.execute(
        text("SELECT count(*) FROM access_decisions WHERE camera_event_id = :e"),
        {"e": camera_event_id},
    ).scalar()


def _count_commands(db, decision_id: int) -> int:
    return db.execute(
        text("SELECT count(*) FROM barrier_commands WHERE decision_id = :d"),
        {"d": decision_id},
    ).scalar()


def test_resolve_manual_open_creates_allowed_manually_and_command(
    pg_db, pilot: PilotFixture
) -> None:
    """Критерий 9(a): manual_open → allowed_manually + durable команда."""
    op = seed_user(pg_db, roles="security_operator")
    pending = seed_pending_review(pg_db, pilot)

    result = resolve_event(
        pg_db,
        event_id=pending.camera_event_id,
        action="manual_open",
        operator_user_id=op,
        reason="оператор открыл вручную",
        barrier_id=pilot.barrier_id,
        decision_id=pending.decision_id,
        source="operator_resolve",
    )

    assert result.status == "allowed_manually"
    assert result.command_id is not None
    assert result.replayed is False
    # Новая append-строка перехода + исходный pending = 2 строки группы.
    assert _count_decisions(pg_db, pending.camera_event_id) == 2
    # Команда привязана к строке перехода (durable доставка).
    assert _count_commands(pg_db, result.decision_id) == 1
    # Текущая строка группы — allowed_manually и supersedes исходный pending.
    tip = pg_db.execute(
        text(
            "SELECT status, supersedes_decision_id FROM access_decisions "
            "WHERE id = :id"
        ),
        {"id": result.decision_id},
    ).first()
    assert tip[0] == "allowed_manually"
    assert tip[1] == pending.decision_id


def test_resolve_manual_open_records_operator_and_reason(
    pg_db, pilot: PilotFixture
) -> None:
    """Критерий 7: manual_opening фиксирует operator_user_id и причину."""
    op = seed_user(pg_db, roles="manager")
    pending = seed_pending_review(pg_db, pilot)

    resolve_event(
        pg_db,
        event_id=pending.camera_event_id,
        action="manual_open",
        operator_user_id=op,
        reason="причина открытия",
        barrier_id=pilot.barrier_id,
        decision_id=pending.decision_id,
        source="operator_resolve",
    )

    row = pg_db.execute(
        text(
            "SELECT operator_user_id, reason, barrier_id FROM manual_openings "
            "WHERE barrier_id = :b"
        ),
        {"b": pilot.barrier_id},
    ).first()
    assert row is not None
    assert row[0] == op
    assert row[1] == "причина открытия"


def test_resolve_deny_creates_denied_manually_no_command(
    pg_db, pilot: PilotFixture
) -> None:
    """Критерий 9(b): deny → denied_manually, команда НЕ создаётся."""
    op = seed_user(pg_db, roles="security_operator")
    pending = seed_pending_review(pg_db, pilot)

    result = resolve_event(
        pg_db,
        event_id=pending.camera_event_id,
        action="deny",
        operator_user_id=op,
        reason="отказ оператора",
        barrier_id=pilot.barrier_id,
        decision_id=pending.decision_id,
        source="operator_resolve",
    )

    assert result.status == "denied_manually"
    assert result.command_id is None
    assert _count_commands(pg_db, result.decision_id) == 0
    # manual_openings для deny не создаётся.
    mo = pg_db.execute(
        text("SELECT count(*) FROM manual_openings WHERE barrier_id = :b"),
        {"b": pilot.barrier_id},
    ).scalar()
    assert mo == 0


def test_resolve_repeat_returns_saved_no_second_command(
    pg_db, pilot: PilotFixture
) -> None:
    """Критерий 9(e): повторная резолюция → сохранённый результат, без 2-й команды."""
    op = seed_user(pg_db, roles="security_operator")
    pending = seed_pending_review(pg_db, pilot)

    first = resolve_event(
        pg_db,
        event_id=pending.camera_event_id,
        action="manual_open",
        operator_user_id=op,
        reason="первый раз",
        barrier_id=pilot.barrier_id,
        decision_id=pending.decision_id,
        source="operator_resolve",
    )
    # Повтор (даже с другим action) возвращает сохранённый allowed_manually.
    second = resolve_event(
        pg_db,
        event_id=pending.camera_event_id,
        action="deny",
        operator_user_id=op,
        reason="повтор",
        barrier_id=pilot.barrier_id,
        decision_id=pending.decision_id,
        source="operator_resolve",
    )

    assert second.status == "allowed_manually"
    assert second.replayed is True
    assert second.command_id == first.command_id
    # Ни второго перехода, ни второй команды.
    assert _count_decisions(pg_db, pending.camera_event_id) == 2
    assert _count_commands(pg_db, first.decision_id) == 1


def test_resolve_append_only_initial_untouched(pg_db, pilot: PilotFixture) -> None:
    """Переход не UPDATE'ит исходный pending: он остаётся pending_review строкой."""
    op = seed_user(pg_db, roles="security_operator")
    pending = seed_pending_review(pg_db, pilot)

    resolve_event(
        pg_db,
        event_id=pending.camera_event_id,
        action="deny",
        operator_user_id=op,
        reason="отказ",
        barrier_id=pilot.barrier_id,
        decision_id=pending.decision_id,
        source="operator_resolve",
    )
    initial = pg_db.execute(
        text("SELECT status FROM access_decisions WHERE id = :id"),
        {"id": pending.decision_id},
    ).scalar()
    assert initial == "pending_review"  # исходная строка не изменена (append-only)


def test_resolve_no_pending_raises(pg_db, pilot: PilotFixture) -> None:
    """Резолюция без активного pending_review → NoPendingReviewError."""
    op = seed_user(pg_db, roles="security_operator")
    with pytest.raises(NoPendingReviewError):
        resolve_event(
            pg_db,
            event_id=999_999,  # нет такого события
            action="deny",
            operator_user_id=op,
            reason="x",
            barrier_id=pilot.barrier_id,
            decision_id=1,
            source="operator_resolve",
        )


def test_resolve_decision_id_mismatch_raises(pg_db, pilot: PilotFixture) -> None:
    """M5: decision_id != текущего pending → DecisionIdMismatch, без перехода/команды."""
    op = seed_user(pg_db, roles="security_operator")
    pending = seed_pending_review(pg_db, pilot)
    with pytest.raises(DecisionIdMismatch):
        resolve_event(
            pg_db,
            event_id=pending.camera_event_id,
            action="manual_open",
            operator_user_id=op,
            reason="ок",
            barrier_id=pilot.barrier_id,
            decision_id=pending.decision_id + 999,  # чужой decision_id
            source="operator_resolve",
        )
    # Ни перехода, ни команды — исходный pending не тронут.
    assert _count_decisions(pg_db, pending.camera_event_id) == 1
    assert _count_commands(pg_db, pending.decision_id) == 0


def test_resolve_manual_open_barrier_deactivated_raises(
    pg_db, pilot: PilotFixture
) -> None:
    """M3/M4: barrier деактивирован → BarrierUnavailableError, не падение NOT NULL."""
    op = seed_user(pg_db, roles="security_operator")
    pending = seed_pending_review(pg_db, pilot)
    pg_db.execute(
        text("UPDATE access_barriers SET is_active = false WHERE id = :b"),
        {"b": pilot.barrier_id},
    )
    pg_db.commit()
    with pytest.raises(BarrierUnavailableError):
        resolve_event(
            pg_db,
            event_id=pending.camera_event_id,
            action="manual_open",
            operator_user_id=op,
            reason="ок",
            barrier_id=pilot.barrier_id,
            decision_id=pending.decision_id,
            source="operator_resolve",
        )
    # Pending не залип: остался единственной (pending_review) строкой.
    assert _count_decisions(pg_db, pending.camera_event_id) == 1
    assert _count_commands(pg_db, pending.decision_id) == 0


def test_resolve_persists_ip_address_in_audit(pg_db, pilot: PilotFixture) -> None:
    """M4-audit (§6.3): ip_address пробрасывается в access_audit_logs."""
    op = seed_user(pg_db, roles="security_operator")
    pending = seed_pending_review(pg_db, pilot)
    resolve_event(
        pg_db,
        event_id=pending.camera_event_id,
        action="deny",
        operator_user_id=op,
        reason="отказ",
        barrier_id=pilot.barrier_id,
        decision_id=pending.decision_id,
        source="operator_resolve",
        ip_address="203.0.113.7",
    )
    ip = pg_db.execute(
        text(
            "SELECT ip_address FROM access_audit_logs WHERE action = 'access.deny'"
        )
    ).scalar()
    assert ip == "203.0.113.7"
