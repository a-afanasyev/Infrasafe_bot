"""Критерий приёмки §15.15: идемпотентная синхронизация offline-событий (§8.4).

После восстановления связи edge шлёт offline-события с исходными ``event_id``;
backend принимает их идемпотентно по ``(controller_id, event_id)``, помечает
source=``edge_offline`` и НЕ превращает их в расход временного пропуска. Повтор не
создаёт дубль. Конфликт/просроченный snapshot фиксируются отдельным полем.

PostgreSQL-only.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.tests.conftest import (
    PilotFixture,
    SigningClient,
    seed_taxi_pass,
    utcnow,
)


def _client(uid: str) -> SigningClient:
    return SigningClient(TestClient(create_app()), uid)


def _event(event_id: str, plate: str = "01T777TT") -> dict:
    return {
        "event_id": event_id,
        "captured_at": utcnow().isoformat(),
        "plate_number": plate,
        "direction": "entry",
        "decision": "deny",
    }


def test_sync_events_stored_as_edge_offline(pg_db, pilot: PilotFixture) -> None:
    """Принятые offline-события попадают в controller_sync_events, source=edge_offline."""
    client = _client(pilot.controller_uid)
    resp = client.post(
        f"/api/v1/access/edge/{pilot.controller_uid}/sync-events",
        json={"events": [_event("off-1"), _event("off-2")]},
    )
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 2

    rows = pg_db.execute(
        text(
            "SELECT event_id, payload->>'source' AS source, conflict "
            "FROM controller_sync_events WHERE controller_id = :c ORDER BY event_id"
        ),
        {"c": pilot.controller_id},
    ).all()
    assert {r[0] for r in rows} == {"off-1", "off-2"}
    assert all(r[1] == "edge_offline" for r in rows)
    assert all(r[2] is False for r in rows)


def test_sync_events_idempotent_repeat(pg_db, pilot: PilotFixture) -> None:
    """Повтор того же (controller_id, event_id) не создаёт дубль (§8.4)."""
    client = _client(pilot.controller_uid)
    body = {"events": [_event("dup-1")]}
    first = client.post(
        f"/api/v1/access/edge/{pilot.controller_uid}/sync-events", json=body
    )
    second = client.post(
        f"/api/v1/access/edge/{pilot.controller_uid}/sync-events", json=body
    )
    assert first.json()["accepted"] == 1
    assert second.json()["accepted"] == 0
    assert second.json()["duplicates"] == 1

    count = pg_db.execute(
        text(
            "SELECT count(*) FROM controller_sync_events "
            "WHERE controller_id = :c AND event_id = 'dup-1'"
        ),
        {"c": pilot.controller_id},
    ).scalar()
    assert count == 1


def test_sync_events_do_not_consume_pass(pg_db, pilot: PilotFixture) -> None:
    """Offline-событие НЕ расходует временный пропуск и не создаёт команду (§8.4)."""
    pass_id = seed_taxi_pass(
        pg_db, pilot, normalized="01T777TT", max_entries=1, used_entries=0
    )
    client = _client(pilot.controller_uid)
    client.post(
        f"/api/v1/access/edge/{pilot.controller_uid}/sync-events",
        json={"events": [_event("off-pass-1", plate="01T777TT")]},
    )
    # used_entries пропуска НЕ изменился.
    used = pg_db.execute(
        text("SELECT used_entries FROM access_passes WHERE id = :i"),
        {"i": pass_id},
    ).scalar()
    assert used == 0
    # Команда открытия шлагбаума НЕ создана.
    cmds = pg_db.execute(
        text("SELECT count(*) FROM barrier_commands WHERE controller_id = :c"),
        {"c": pilot.controller_id},
    ).scalar()
    assert cmds == 0


def test_sync_events_conflict_flagged(pg_db, pilot: PilotFixture) -> None:
    """Просроченный snapshot/конфликт фиксируется отдельным полем (§8.4)."""
    client = _client(pilot.controller_uid)
    ev = _event("conf-1")
    ev["snapshot_expired"] = True
    ev["conflict"] = True
    client.post(
        f"/api/v1/access/edge/{pilot.controller_uid}/sync-events",
        json={"events": [ev]},
    )
    row = pg_db.execute(
        text(
            "SELECT conflict, snapshot_expired FROM controller_sync_events "
            "WHERE controller_id = :c AND event_id = 'conf-1'"
        ),
        {"c": pilot.controller_id},
    ).first()
    assert row[0] is True
    assert row[1] is True
