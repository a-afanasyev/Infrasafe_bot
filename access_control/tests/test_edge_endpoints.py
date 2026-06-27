"""Edge equipment-endpoint'ы Ф6: heartbeat (§8.2 clock-drift) и access-snapshot (§8.2).

Дополнение к критериям 17/18: heartbeat пишет clock offset и сигналит fail_closed
при |offset|>30c; access-snapshot отдаёт ПОДПИСАННЫЙ fail_closed-snapshot без списка
номеров только аутентифицированному контроллеру.

PostgreSQL-only (pilot-фикстуры).
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.edge.snapshot_verifier import verify_snapshot
from access_control.services.snapshot_signing import current_key_id, public_key_bytes
from access_control.tests.conftest import PilotFixture, SigningClient


def _client(uid: str) -> SigningClient:
    return SigningClient(TestClient(create_app()), uid)


def test_heartbeat_records_offset(pg_db, pilot: PilotFixture) -> None:
    """heartbeat пишет last_heartbeat_at + clock_offset_ms; малый offset → без алертов."""
    client = _client(pilot.controller_uid)
    resp = client.post(
        f"/api/v1/access/edge/{pilot.controller_uid}/heartbeat",
        json={"clock_offset_ms": 1200, "status": "connected"},
    )
    assert resp.status_code == 200
    out = resp.json()
    assert out["fail_closed"] is False
    assert out["warning"] is False

    row = pg_db.execute(
        text(
            "SELECT last_heartbeat_at, clock_offset_ms FROM edge_controllers "
            "WHERE id = :i"
        ),
        {"i": pilot.controller_id},
    ).first()
    assert row[0] is not None
    assert row[1] == 1200


def test_heartbeat_drift_over_30s_fail_closed(pg_db, pilot: PilotFixture) -> None:
    """|offset|>30000мс → fail_closed (§8.2)."""
    client = _client(pilot.controller_uid)
    resp = client.post(
        f"/api/v1/access/edge/{pilot.controller_uid}/heartbeat",
        json={"clock_offset_ms": 45000, "status": "connected"},
    )
    assert resp.status_code == 200
    assert resp.json()["fail_closed"] is True


def test_heartbeat_drift_over_5s_warning(pg_db, pilot: PilotFixture) -> None:
    """5000<|offset|≤30000мс в connected → warning, но не fail_closed (§8.2)."""
    client = _client(pilot.controller_uid)
    resp = client.post(
        f"/api/v1/access/edge/{pilot.controller_uid}/heartbeat",
        json={"clock_offset_ms": 9000, "status": "connected"},
    )
    out = resp.json()
    assert out["fail_closed"] is False
    assert out["warning"] is True


def test_access_snapshot_signed_and_verifiable(pg_db, pilot: PilotFixture) -> None:
    """access-snapshot подписан, проверяем pinned-ключом; fail_closed без списка номеров."""
    client = _client(pilot.controller_uid)
    resp = client.get(
        f"/api/v1/access/edge/{pilot.controller_uid}/access-snapshot"
    )
    assert resp.status_code == 200
    snap = resp.json()
    assert snap["offline_mode"] == "fail_closed"
    assert snap["controller_uid"] == pilot.controller_uid
    assert "signature" in snap and "key_id" in snap
    assert "expires_at" in snap and "issued_at" in snap
    # Нет разрешающего списка номеров (fail_closed пилот, §8.2).
    assert "vehicles" not in snap and "plates" not in snap
    # Подпись проверяется pinned-ключом, но въезд не открывает (reject-only).
    result = verify_snapshot(
        snap, pinned_key_id=current_key_id(), pinned_public_key=public_key_bytes()
    )
    assert result.accepted is True
    assert result.entry_allowed is False


def test_access_snapshot_only_own_controller(pg_db, pilot: PilotFixture, pilot_b) -> None:
    """Контроллер получает snapshot ТОЛЬКО своих данных (§9.1: не чужую зону)."""
    client = _client(pilot.controller_uid)
    resp = client.get(
        f"/api/v1/access/edge/{pilot.controller_uid}/access-snapshot"
    )
    assert resp.json()["controller_uid"] == pilot.controller_uid
    # Запрос на путь чужого контроллера (подписан как A) → 403.
    resp_foreign = client.get(
        f"/api/v1/access/edge/{pilot_b.controller_uid}/access-snapshot"
    )
    assert resp_foreign.status_code == 403
