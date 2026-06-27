"""Критерий приёмки §15.17: device authentication на edge-endpoint'ах (§9.1).

Edge без валидного device credential не принимает snapshot и команды. Покрытие
полной матрицы §9.1 на реальных endpoint'ах (anpr / access-snapshot / commands/next
/ ack): отсутствие/неверная подпись, неверный api_key, чужой IP, неактивный/
decommissioned контроллер, replay nonce, протухший timestamp, изменённое тело,
изоляция по controller_id. Валидная подпись — проходит.

PostgreSQL-only (использует pilot-фикстуры реального DATABASE_URL).
"""
from __future__ import annotations

import time
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.tests.conftest import (
    PilotFixture,
    SigningClient,
    device_headers,
    seed_barrier_command,
    seed_permanent_vehicle,
    utcnow,
)


def _raw() -> TestClient:
    return TestClient(create_app())


def _anpr_body(pilot: PilotFixture, *, event_id: str, plate: str) -> dict:
    return {
        "controller_uid": pilot.controller_uid,
        "event_id": event_id,
        "zone_id": pilot.zone_id,
        "gate_id": pilot.gate_id,
        "camera_id": pilot.camera_id,
        "barrier_id": pilot.barrier_id,
        "plate_number": plate,
        "direction": "entry",
        "confidence": 0.95,
        "captured_at": utcnow().isoformat(),
    }


# ----------------------------- отсутствие подписи -----------------------------


def test_anpr_missing_credentials_401(pg_db, pilot: PilotFixture) -> None:
    """ANPR без device-auth заголовков → 401."""
    resp = _raw().post(
        "/api/v1/access/camera-events/anpr",
        json=_anpr_body(pilot, event_id="noauth-1", plate="01A001AA"),
    )
    assert resp.status_code == 401


def test_snapshot_missing_credentials_401(pg_db, pilot: PilotFixture) -> None:
    resp = _raw().get(
        f"/api/v1/access/edge/{pilot.controller_uid}/access-snapshot"
    )
    assert resp.status_code == 401


def test_commands_next_missing_credentials_401(pg_db, pilot: PilotFixture) -> None:
    resp = _raw().get(
        f"/api/v1/access/edge/{pilot.controller_uid}/commands/next"
    )
    assert resp.status_code == 401


def test_ack_missing_credentials_401(pg_db, pilot: PilotFixture) -> None:
    cmd_id = seed_barrier_command(pg_db, pilot, status="pending")
    resp = _raw().post(
        f"/api/v1/access/edge/{pilot.controller_uid}/commands/{cmd_id}/ack",
        json={"lease_token": "x", "result": {"opened": True}},
    )
    assert resp.status_code == 401


# ----------------------------- валидная подпись -----------------------------


def test_anpr_valid_signature_allows(pg_db, pilot: PilotFixture) -> None:
    seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA")
    client = SigningClient(_raw(), pilot.controller_uid)
    resp = client.post(
        "/api/v1/access/camera-events/anpr",
        json=_anpr_body(pilot, event_id="ok-1", plate="01A001AA"),
    )
    assert resp.status_code == 200
    assert resp.json()["decision"] == "allow"


def test_snapshot_valid_signature_ok(pg_db, pilot: PilotFixture) -> None:
    client = SigningClient(_raw(), pilot.controller_uid)
    resp = client.get(
        f"/api/v1/access/edge/{pilot.controller_uid}/access-snapshot"
    )
    assert resp.status_code == 200


def test_commands_next_valid_signature_204(pg_db, pilot: PilotFixture) -> None:
    client = SigningClient(_raw(), pilot.controller_uid)
    resp = client.get(
        f"/api/v1/access/edge/{pilot.controller_uid}/commands/next"
    )
    assert resp.status_code == 204


# ----------------------------- неверный api_key -----------------------------


def test_wrong_api_key_401(pg_db, pilot: PilotFixture) -> None:
    """Подпись валидна по структуре, но api_key не совпадает с хэшем → 401."""
    client = SigningClient(_raw(), pilot.controller_uid, api_key="totally-wrong-key")
    resp = client.get(
        f"/api/v1/access/edge/{pilot.controller_uid}/access-snapshot"
    )
    assert resp.status_code == 401


# ----------------------------- чужой IP allowlist -----------------------------


def test_foreign_ip_403(pg_db, pilot: PilotFixture) -> None:
    """IP клиента не в allowlist контроллера → 403 (§9.1)."""
    pg_db.execute(
        text("UPDATE edge_controllers SET ip_allowlist = :al WHERE id = :i"),
        {"al": '["10.0.0.1"]', "i": pilot.controller_id},
    )
    pg_db.commit()
    client = SigningClient(_raw(), pilot.controller_uid)
    resp = client.get(
        f"/api/v1/access/edge/{pilot.controller_uid}/access-snapshot"
    )
    assert resp.status_code == 403


# ------------------------- неактивный / decommissioned -------------------------


def test_inactive_controller_401(pg_db, pilot: PilotFixture) -> None:
    pg_db.execute(
        text("UPDATE edge_controllers SET is_active = false WHERE id = :i"),
        {"i": pilot.controller_id},
    )
    pg_db.commit()
    client = SigningClient(_raw(), pilot.controller_uid)
    resp = client.get(
        f"/api/v1/access/edge/{pilot.controller_uid}/access-snapshot"
    )
    assert resp.status_code == 401


def test_decommissioned_controller_401(pg_db, pilot: PilotFixture) -> None:
    pg_db.execute(
        text("UPDATE edge_controllers SET status = 'decommissioned' WHERE id = :i"),
        {"i": pilot.controller_id},
    )
    pg_db.commit()
    client = SigningClient(_raw(), pilot.controller_uid)
    resp = client.get(
        f"/api/v1/access/edge/{pilot.controller_uid}/commands/next"
    )
    assert resp.status_code == 401


# ----------------------------- replay nonce -----------------------------


def test_replay_nonce_rejected_401(pg_db, pilot: PilotFixture) -> None:
    """Один и тот же nonce дважды → второй запрос 401 (anti-replay §9.1)."""
    client = _raw()
    ts = int(time.time())
    nonce = uuid.uuid4().hex
    path = f"/api/v1/access/edge/{pilot.controller_uid}/access-snapshot"
    headers = device_headers(
        pilot.controller_uid, method="GET", path=path, body=b"",
        timestamp=ts, nonce=nonce,
    )
    first = client.get(path, headers=headers)
    second = client.get(path, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 401


# ----------------------------- протухший timestamp -----------------------------


def test_stale_timestamp_rejected_401(pg_db, pilot: PilotFixture) -> None:
    """timestamp вне окна свежести → 401 (§9.1)."""
    client = _raw()
    path = f"/api/v1/access/edge/{pilot.controller_uid}/access-snapshot"
    headers = device_headers(
        pilot.controller_uid, method="GET", path=path, body=b"",
        timestamp=int(time.time()) - 100000,
    )
    resp = client.get(path, headers=headers)
    assert resp.status_code == 401


# ----------------------------- изменённое тело -----------------------------


def test_tampered_body_rejected_401(pg_db, pilot: PilotFixture) -> None:
    """Заголовки подписаны под одно тело, отправлено другое → HMAC mismatch → 401."""
    client = _raw()
    path = "/api/v1/access/camera-events/anpr"
    signed_body = _anpr_body(pilot, event_id="tamper-1", plate="01A001AA")
    import json as _json

    body_bytes = _json.dumps(signed_body).encode("utf-8")
    headers = device_headers(
        pilot.controller_uid, method="POST", path=path, body=body_bytes
    )
    headers["content-type"] = "application/json"
    tampered = dict(signed_body)
    tampered["plate_number"] = "99Z999ZZ"  # тело изменено после подписи
    resp = client.post(
        path, content=_json.dumps(tampered).encode("utf-8"), headers=headers
    )
    assert resp.status_code == 401


# ----------------------------- IP allowlist: CIDR (порт из B) -----------------------------


def test_ip_allowlist_supports_cidr() -> None:
    """allowlist с CIDR-подсетью матчит IP внутри неё и отвергает вне (порт из B, §9.1)."""
    from access_control.services.device_auth import _client_ip_allowed

    class _Ctrl:
        ip_allowlist = ["10.0.0.0/24"]

    assert _client_ip_allowed(_Ctrl(), "10.0.0.7") is True
    assert _client_ip_allowed(_Ctrl(), "10.0.1.7") is False


def test_ip_allowlist_exact_match_still_works() -> None:
    """Точные IP-записи продолжают работать (обратная совместимость, §9.1)."""
    from access_control.services.device_auth import _client_ip_allowed

    class _Ctrl:
        ip_allowlist = ["192.168.1.5"]

    assert _client_ip_allowed(_Ctrl(), "192.168.1.5") is True
    assert _client_ip_allowed(_Ctrl(), "192.168.1.6") is False


# ----------------------------- изоляция controller_id -----------------------------


def test_controller_path_mismatch_403(pg_db, pilot: PilotFixture, pilot_b) -> None:
    """Контроллер A подписывает запрос на путь контроллера B → 403 (§9.1 изоляция)."""
    client = _raw()
    path = f"/api/v1/access/edge/{pilot_b.controller_uid}/access-snapshot"
    # Подпись валидна как A, но путь принадлежит B.
    headers = device_headers(pilot.controller_uid, method="GET", path=path, body=b"")
    resp = client.get(path, headers=headers)
    assert resp.status_code == 403
