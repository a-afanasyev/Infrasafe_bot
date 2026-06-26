"""Durable channel: lease/ack barrier_commands (§9.2, §13.1). PostgreSQL-only.

Покрывает атомарный lease (FOR UPDATE SKIP LOCKED), изоляцию по controller_id
(контроллер видит только свои команды), compare-and-set ACK, идемпотентный
повторный ACK и отклонение чужого/протухшего lease_token.
"""
from __future__ import annotations

import datetime as dt
import uuid

import pytest

from access_control.api.commands import (
    AckConflict,
    ack_command,
    lease_next_command,
)
from access_control.tests.conftest import PilotFixture, seed_barrier_command


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def test_lease_returns_pending_and_marks_leased(pg_db, pilot: PilotFixture) -> None:
    cmd_id = seed_barrier_command(pg_db, pilot, status="pending")
    leased = lease_next_command(pg_db, pilot.controller_id)
    assert leased is not None
    assert str(leased.command_id) == cmd_id
    assert leased.barrier_id == pilot.barrier_id
    assert leased.lease_token is not None
    row = pg_db.execute(
        __import__("sqlalchemy").text(
            "SELECT status, attempts, leased_at FROM barrier_commands "
            "WHERE command_id = :c"
        ),
        {"c": cmd_id},
    ).first()
    assert row[0] == "leased"
    assert row[1] == 1  # attempts инкрементнут
    assert row[2] is not None  # leased_at проставлен


def test_lease_empty_queue_returns_none(pg_db, pilot: PilotFixture) -> None:
    assert lease_next_command(pg_db, pilot.controller_id) is None


def test_lease_does_not_issue_same_command_twice(pg_db, pilot: PilotFixture) -> None:
    """Две команды → два разных lease; третий lease пуст (нет двойной выдачи)."""
    c1 = seed_barrier_command(pg_db, pilot, status="pending")
    c2 = seed_barrier_command(pg_db, pilot, status="pending")
    first = lease_next_command(pg_db, pilot.controller_id)
    second = lease_next_command(pg_db, pilot.controller_id)
    third = lease_next_command(pg_db, pilot.controller_id)
    leased_ids = {str(first.command_id), str(second.command_id)}
    assert leased_ids == {c1, c2}
    assert third is None


def test_lease_isolated_by_controller(pg_db, pilot: PilotFixture, pilot_b) -> None:
    """ControllerA не лизит команды ControllerB (§9.1)."""
    seed_barrier_command(pg_db, pilot_b, status="pending")
    # У controllerA нет своих команд → пусто, хотя у B есть pending.
    assert lease_next_command(pg_db, pilot.controller_id) is None
    # А свою команду B лизит нормально.
    leased_b = lease_next_command(pg_db, pilot_b.controller_id)
    assert leased_b is not None


def test_lease_skips_expired_command(pg_db, pilot: PilotFixture) -> None:
    seed_barrier_command(
        pg_db, pilot, status="pending", expires_at=_utcnow() - dt.timedelta(seconds=5)
    )
    assert lease_next_command(pg_db, pilot.controller_id) is None


def test_ack_compare_and_set_marks_acked(pg_db, pilot: PilotFixture) -> None:
    seed_barrier_command(pg_db, pilot, status="pending")
    leased = lease_next_command(pg_db, pilot.controller_id)
    outcome = ack_command(
        pg_db,
        pilot.controller_id,
        str(leased.command_id),
        str(leased.lease_token),
        {"opened": True},
    )
    assert outcome.status == "acked"
    assert outcome.replayed is False
    assert outcome.result == {"opened": True}


def test_ack_replay_returns_saved_result_no_reexec(pg_db, pilot: PilotFixture) -> None:
    """Повторный ACK после потери ответа возвращает сохранённый результат (крит. 5)."""
    seed_barrier_command(pg_db, pilot, status="pending")
    leased = lease_next_command(pg_db, pilot.controller_id)
    token = str(leased.lease_token)
    first = ack_command(
        pg_db, pilot.controller_id, str(leased.command_id), token, {"opened": True}
    )
    second = ack_command(
        pg_db, pilot.controller_id, str(leased.command_id), token, {"opened": True}
    )
    assert first.replayed is False
    assert second.replayed is True
    assert second.result == {"opened": True}


def test_ack_wrong_lease_token_conflict(pg_db, pilot: PilotFixture) -> None:
    seed_barrier_command(pg_db, pilot, status="pending")
    leased = lease_next_command(pg_db, pilot.controller_id)
    raised = False
    try:
        ack_command(
            pg_db,
            pilot.controller_id,
            str(leased.command_id),
            "00000000-0000-0000-0000-000000000000",
            {"opened": True},
        )
    except AckConflict:
        raised = True
    assert raised


def test_ack_foreign_controller_conflict(pg_db, pilot: PilotFixture, pilot_b) -> None:
    """ACK чужим controller_id отклоняется (§9.1)."""
    seed_barrier_command(pg_db, pilot, status="pending")
    leased = lease_next_command(pg_db, pilot.controller_id)
    with pytest.raises(AckConflict):
        ack_command(
            pg_db,
            pilot_b.controller_id,  # чужой контроллер
            str(leased.command_id),
            str(leased.lease_token),
            {"opened": True},
        )


def test_ack_nonexistent_command_conflict(pg_db, pilot: PilotFixture) -> None:
    """ACK несуществующего command_id → AckConflict (нет команды для CAS, §9.2)."""
    with pytest.raises(AckConflict):
        ack_command(
            pg_db,
            pilot.controller_id,
            str(uuid.uuid4()),  # команды с таким id нет
            str(uuid.uuid4()),
            {"opened": True},
        )
