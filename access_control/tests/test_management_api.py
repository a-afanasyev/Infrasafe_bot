"""Ф?: WRITE-эндпоинты менеджера (§13.2, §6.2, §4 п.7). PostgreSQL-only.

Покрывает менеджерские операции записи поверх общей базы access_control:

* ``POST /api/v1/access/vehicles`` — создать постоянный авто (+ привязка к
  квартире + правило зоны), 409 на дубль активного номера;
* ``PATCH /api/v1/access/vehicles/{id}/status`` — active|blocked|archived
  (blocked требует reason);
* ``POST /api/v1/access/passes/taxi`` — taxi-пропуск (§13.2);
* ``POST /api/v1/access/requests/{id}/review`` — рассмотрение заявки жителя
  (approve активирует постоянный авто §4 п.7; reject; идемпотентно).

RBAC (§6.2/§6.3): manager/system_admin — да; security_operator/applicant/
executor/inspector → 403; без auth → 401.

Интеграция с Decision Engine (§7): после create/approve ANPR того же номера даёт
allow; после block — deny vehicle_blocked; taxi-pass — allow один раз. Аудит
(§9.7): каждое изменение пишет append-only строку access_audit_logs.
"""
from __future__ import annotations

import datetime as dt
import types

from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.services.ingestion import AnprIngestInput, ingest_anpr
from access_control.tests.conftest import PilotFixture, seed_user, utcnow
from uk_management_bot.api.dependencies import get_current_user

PLATE = "01A123BC"


def _fake_user(uid: int, role: str, status: str = "approved"):
    import json

    return lambda: types.SimpleNamespace(
        id=uid, roles=json.dumps([role]), active_role=role, status=status
    )


def _client(uid: int, role: str, status: str = "approved") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, role, status)
    return TestClient(app)


def _ingest(db, pilot: PilotFixture, *, plate: str = PLATE, event_id: str,
            captured_at: dt.datetime | None = None):
    return ingest_anpr(
        db,
        AnprIngestInput(
            controller_id=pilot.controller_id,
            event_id=event_id,
            zone_id=pilot.zone_id,
            gate_id=pilot.gate_id,
            camera_id=pilot.camera_id,
            barrier_id=pilot.barrier_id,
            plate_number_original=plate,
            direction="entry",
            confidence=0.99,
            captured_at=captured_at or utcnow(),
        ),
    )


def _seed_request(db, pilot: PilotFixture, *, creator_id: int, plate: str = PLATE,
                  relation_type: str = "owner") -> int:
    rid = db.execute(
        text(
            "INSERT INTO resident_access_requests "
            "(apartment_id, created_by_user_id, plate_number_original, "
            " plate_number_normalized, relation_type, status) "
            "VALUES (:a, :c, :po, :pn, :rt, 'pending') RETURNING id"
        ),
        {"a": pilot.apartment_id, "c": creator_id, "po": plate, "pn": plate,
         "rt": relation_type},
    ).scalar()
    db.commit()
    return rid


# ------------------------------ router wiring ------------------------------


def test_management_router_registered() -> None:
    paths = {route.path for route in create_app().routes}
    assert "/api/v1/access/vehicles" in paths
    assert "/api/v1/access/vehicles/{vehicle_id}/status" in paths
    assert "/api/v1/access/passes/taxi" in paths
    assert "/api/v1/access/requests/{request_id}/review" in paths


# ------------------------------ RBAC ------------------------------


def test_create_vehicle_requires_auth_401(pg_db, pilot: PilotFixture) -> None:
    resp = TestClient(create_app()).post(
        "/api/v1/access/vehicles", json={"plate_number_original": PLATE}
    )
    assert resp.status_code == 401


def test_create_vehicle_security_operator_403(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="security_operator")
    resp = _client(uid, "security_operator").post(
        "/api/v1/access/vehicles", json={"plate_number_original": PLATE}
    )
    assert resp.status_code == 403


def test_create_vehicle_applicant_403(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="applicant")
    resp = _client(uid, "applicant").post(
        "/api/v1/access/vehicles", json={"plate_number_original": PLATE}
    )
    assert resp.status_code == 403


def test_taxi_pass_security_operator_403(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="security_operator")
    resp = _client(uid, "security_operator").post(
        "/api/v1/access/passes/taxi",
        json={"apartment_id": pilot.apartment_id, "zone_id": pilot.zone_id,
              "valid_until": utcnow().isoformat()},
    )
    assert resp.status_code == 403


def test_review_inspector_403(pg_db, pilot: PilotFixture) -> None:
    creator = seed_user(pg_db, roles="applicant")
    uid = seed_user(pg_db, roles="inspector")
    rid = _seed_request(pg_db, pilot, creator_id=creator)
    resp = _client(uid, "inspector").post(
        f"/api/v1/access/requests/{rid}/review", json={"action": "reject"}
    )
    assert resp.status_code == 403


# ------------------------------ create vehicle ------------------------------


def test_create_vehicle_full_then_anpr_allows(pg_db, pilot: PilotFixture) -> None:
    """§6.2 + §7: создать авто с квартирой и правилом зоны → ANPR даёт allow."""
    uid = seed_user(pg_db, roles="manager")
    resp = _client(uid, "manager").post(
        "/api/v1/access/vehicles",
        json={
            "plate_number_original": PLATE,
            "brand": "Chevrolet",
            "model": "Cobalt",
            "apartment_id": pilot.apartment_id,
            "relation_type": "owner",
            "zone_id": pilot.zone_id,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "active"
    assert body["plate_number_normalized"] == PLATE
    assert body["brand"] == "Chevrolet"
    assert len(body["apartments"]) == 1
    assert body["apartments"][0]["status"] == "active"

    result = _ingest(pg_db, pilot, event_id="ev-create-1")
    assert result.decision == "allow"
    assert result.reason == "permanent_vehicle_allowed"


def test_create_vehicle_writes_audit(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    resp = _client(uid, "manager").post(
        "/api/v1/access/vehicles", json={"plate_number_original": PLATE}
    )
    assert resp.status_code == 201
    row = pg_db.execute(
        text(
            "SELECT actor_user_id, action, row_hash FROM access_audit_logs "
            "WHERE action = 'access.vehicle_create'"
        )
    ).first()
    assert row is not None
    assert row[0] == uid
    assert row[2] is not None  # hash-chain заполнен


def test_create_vehicle_duplicate_active_409(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    r1 = client.post("/api/v1/access/vehicles", json={"plate_number_original": PLATE})
    assert r1.status_code == 201
    r2 = client.post("/api/v1/access/vehicles", json={"plate_number_original": PLATE})
    assert r2.status_code == 409


# ------------------------------ block vehicle ------------------------------


def test_block_vehicle_then_anpr_denies(pg_db, pilot: PilotFixture) -> None:
    """§6.2: блокировка авто → последующий ANPR даёт deny vehicle_blocked."""
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    created = client.post(
        "/api/v1/access/vehicles",
        json={"plate_number_original": PLATE, "apartment_id": pilot.apartment_id,
              "zone_id": pilot.zone_id},
    ).json()
    vid = created["id"]

    # До блокировки — allow.
    allow = _ingest(pg_db, pilot, event_id="ev-blk-allow",
                    captured_at=utcnow() - dt.timedelta(seconds=60))
    assert allow.decision == "allow"

    resp = client.patch(
        f"/api/v1/access/vehicles/{vid}/status",
        json={"status": "blocked", "reason": "долг по парковке"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "blocked"
    assert resp.json()["blocked_reason"] == "долг по парковке"

    deny = _ingest(pg_db, pilot, event_id="ev-blk-deny", captured_at=utcnow())
    assert deny.decision == "deny"
    assert deny.reason == "vehicle_blocked"


def test_block_requires_reason_422(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    vid = client.post(
        "/api/v1/access/vehicles", json={"plate_number_original": PLATE}
    ).json()["id"]
    resp = client.patch(
        f"/api/v1/access/vehicles/{vid}/status", json={"status": "blocked"}
    )
    assert resp.status_code == 422


def test_status_unknown_vehicle_404(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    resp = _client(uid, "manager").patch(
        "/api/v1/access/vehicles/999999/status", json={"status": "archived"}
    )
    assert resp.status_code == 404


# ------------------------------ taxi pass ------------------------------


def test_taxi_pass_create_then_anpr_allows_once(pg_db, pilot: PilotFixture) -> None:
    """§13.2 + §7: taxi-пропуск → ANPR allow один раз, затем pass_already_used."""
    uid = seed_user(pg_db, roles="manager")
    resp = _client(uid, "manager").post(
        "/api/v1/access/passes/taxi",
        json={
            "apartment_id": pilot.apartment_id,
            "plate_number_original": PLATE,
            "zone_id": pilot.zone_id,
            "valid_until": (utcnow() + dt.timedelta(hours=2)).isoformat(),
            "max_entries": 1,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["pass_type"] == "taxi"
    assert body["status"] == "active"
    assert body["used_entries"] == 0

    first = _ingest(pg_db, pilot, event_id="ev-taxi-1",
                    captured_at=utcnow() - dt.timedelta(seconds=60))
    assert first.decision == "allow"
    assert first.reason == "temporary_pass_allowed"
    second = _ingest(pg_db, pilot, event_id="ev-taxi-2", captured_at=utcnow())
    assert second.decision == "deny"
    assert second.reason == "pass_already_used"


# ------------------------------ review request ------------------------------


def test_review_approve_activates_vehicle(pg_db, pilot: PilotFixture) -> None:
    """§4 п.7: approve активирует постоянный авто → ANPR allow."""
    creator = seed_user(pg_db, roles="applicant")
    uid = seed_user(pg_db, roles="manager")
    rid = _seed_request(pg_db, pilot, creator_id=creator)
    resp = _client(uid, "manager").post(
        f"/api/v1/access/requests/{rid}/review",
        json={"action": "approve", "zone_id": pilot.zone_id, "comment": "ок"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "approved"
    assert body["vehicle_id"] is not None

    # Заявка обновлена в БД.
    row = pg_db.execute(
        text("SELECT status, reviewed_by_user_id FROM resident_access_requests "
             "WHERE id = :i"),
        {"i": rid},
    ).first()
    assert row[0] == "approved"
    assert row[1] == uid

    result = _ingest(pg_db, pilot, event_id="ev-approve-1")
    assert result.decision == "allow"
    assert result.reason == "permanent_vehicle_allowed"


def test_review_reject_sets_status(pg_db, pilot: PilotFixture) -> None:
    creator = seed_user(pg_db, roles="applicant")
    uid = seed_user(pg_db, roles="manager")
    rid = _seed_request(pg_db, pilot, creator_id=creator)
    resp = _client(uid, "manager").post(
        f"/api/v1/access/requests/{rid}/review",
        json={"action": "reject", "comment": "нет документов"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rejected"
    status_db = pg_db.execute(
        text("SELECT status FROM resident_access_requests WHERE id = :i"), {"i": rid}
    ).scalar()
    assert status_db == "rejected"


def test_review_idempotent_replay(pg_db, pilot: PilotFixture) -> None:
    """Повторный review завершённой заявки → сохранённый результат, без дублей."""
    creator = seed_user(pg_db, roles="applicant")
    uid = seed_user(pg_db, roles="manager")
    rid = _seed_request(pg_db, pilot, creator_id=creator)
    client = _client(uid, "manager")
    r1 = client.post(
        f"/api/v1/access/requests/{rid}/review",
        json={"action": "approve", "zone_id": pilot.zone_id},
    )
    assert r1.status_code == 200
    assert r1.json()["replayed"] is False
    vid1 = r1.json()["vehicle_id"]

    r2 = client.post(
        f"/api/v1/access/requests/{rid}/review",
        json={"action": "approve", "zone_id": pilot.zone_id},
    )
    assert r2.status_code == 200
    assert r2.json()["replayed"] is True
    assert r2.json()["vehicle_id"] == vid1

    # Ровно один авто и одно правило зоны (повтор не создал дублей).
    n_vehicles = pg_db.execute(
        text("SELECT count(*) FROM vehicles WHERE plate_number_normalized = :p"),
        {"p": PLATE},
    ).scalar()
    assert n_vehicles == 1
    n_rules = pg_db.execute(
        text("SELECT count(*) FROM access_rules WHERE vehicle_id = :v"), {"v": vid1}
    ).scalar()
    assert n_rules == 1


def test_review_unknown_request_404(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    resp = _client(uid, "manager").post(
        "/api/v1/access/requests/999999/review", json={"action": "reject"}
    )
    assert resp.status_code == 404


def test_review_writes_audit(pg_db, pilot: PilotFixture) -> None:
    creator = seed_user(pg_db, roles="applicant")
    uid = seed_user(pg_db, roles="manager")
    rid = _seed_request(pg_db, pilot, creator_id=creator)
    _client(uid, "manager").post(
        f"/api/v1/access/requests/{rid}/review",
        json={"action": "approve", "zone_id": pilot.zone_id},
    )
    action = pg_db.execute(
        text("SELECT action FROM access_audit_logs "
             "WHERE action = 'access.request_approve'")
    ).scalar()
    assert action == "access.request_approve"
