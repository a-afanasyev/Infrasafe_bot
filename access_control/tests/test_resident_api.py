"""APPLICANT-API контроля доступа для жителей (§6.4, §16.2). PostgreSQL-only.

Личный кабинет жителя поверх общей базы access_control. Эндпоинты — единый API
для бота И TWA (§4 п.4-5): клиент без бизнес-логики.

Покрывает (§6.4):
* ``GET  /api/v1/access/my/vehicles``  — авто своих approved-квартир;
* ``GET  /api/v1/access/my/passes``    — пропуска своих квартир / созданные собой;
* ``GET  /api/v1/access/my/requests``  — заявки свои / по своим квартирам;
* ``GET  /api/v1/access/my/events``    — события по своим авто/квартирам;
* ``POST /api/v1/access/requests``     — заявка на постоянный авто (pending);
* ``POST /api/v1/access/passes``       — временный пропуск (taxi|guest|delivery);
* ``POST /api/v1/access/passes/{id}/cancel`` — отмена своего пропуска (revoked).

КЛЮЧЕВАЯ ГРАНИЦА (§6.4): житель видит/создаёт ТОЛЬКО для approved-квартир
(``user_apartments.status='approved'``). Любой чужой ``apartment_id`` → 403;
``/my/*`` отдаёт только свои данные (проверка изоляции на 2 пользователях). Без
auth → 401; не-applicant → 403.
"""
from __future__ import annotations

import datetime as dt
import types

from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.services.ingestion import AnprIngestInput, ingest_anpr
from access_control.tests.conftest import (
    PilotFixture,
    _seed_apartment,
    seed_user,
    utcnow,
)
from uk_management_bot.api.dependencies import get_current_user

PLATE = "01A777BC"
PLATE_B = "01B888CD"


# ------------------------------ auth / client ------------------------------


def _fake_user(uid: int, role: str = "applicant", status: str = "approved"):
    import json

    return lambda: types.SimpleNamespace(
        id=uid, roles=json.dumps([role]), active_role=role, status=status
    )


def _client(uid: int, role: str = "applicant", status: str = "approved") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, role, status)
    return TestClient(app)


# ------------------------------ seed helpers ------------------------------


def _link_user_apartment(db, user_id: int, apartment_id: int, status: str = "approved") -> None:
    db.execute(
        text(
            "INSERT INTO user_apartments (user_id, apartment_id, status, is_owner, is_primary) "
            "VALUES (:u, :a, :s, false, true)"
        ),
        {"u": user_id, "a": apartment_id, "s": status},
    )
    db.commit()


def _yard_of(db, apartment_id: int) -> int:
    return db.execute(
        text(
            "SELECT b.yard_id FROM apartments a JOIN buildings b ON b.id = a.building_id "
            "WHERE a.id = :a"
        ),
        {"a": apartment_id},
    ).scalar_one()


def _link_zone_yard(db, zone_id: int, yard_id: int) -> None:
    db.execute(
        text("INSERT INTO parking_zone_yards (zone_id, yard_id) VALUES (:z, :y)"),
        {"z": zone_id, "y": yard_id},
    )
    db.commit()


def _seed_vehicle(db, apartment_id: int, normalized: str, *,
                  status: str = "active", link_status: str = "active") -> int:
    vid = db.execute(
        text(
            "INSERT INTO vehicles "
            "(plate_number_original, plate_number_normalized, plate_country, status) "
            "VALUES (:p, :p, 'UZ', :s) RETURNING id"
        ),
        {"p": normalized, "s": status},
    ).scalar_one()
    db.execute(
        text(
            "INSERT INTO vehicle_apartments "
            "(vehicle_id, apartment_id, relation_type, status) "
            "VALUES (:v, :a, 'owner', :ls)"
        ),
        {"v": vid, "a": apartment_id, "ls": link_status},
    )
    db.commit()
    return vid


def _seed_request(db, apartment_id: int, creator_id: int, *, plate: str = PLATE,
                  status: str = "pending") -> int:
    rid = db.execute(
        text(
            "INSERT INTO resident_access_requests "
            "(apartment_id, created_by_user_id, plate_number_original, "
            " plate_number_normalized, relation_type, status) "
            "VALUES (:a, :c, :po, :pn, 'owner', :st) RETURNING id"
        ),
        {"a": apartment_id, "c": creator_id, "po": plate, "pn": plate, "st": status},
    ).scalar_one()
    db.commit()
    return rid


def _seed_pass(db, apartment_id: int, *, created_by: int | None = None,
               normalized: str = PLATE, status: str = "active",
               pass_type: str = "taxi") -> int:
    pid = db.execute(
        text(
            "INSERT INTO access_passes "
            "(apartment_id, created_by_user_id, pass_type, plate_number_original, "
            " plate_number_normalized, max_entries, used_entries, status, source) "
            "VALUES (:a, :c, :pt, :p, :p, 1, 0, :st, 'resident') RETURNING id"
        ),
        {"a": apartment_id, "c": created_by, "pt": pass_type, "p": normalized, "st": status},
    ).scalar_one()
    db.commit()
    return pid


def _seed_event(db, *, controller_id: int, event_id: str, apartment_id: int | None = None,
                normalized: str | None = None, zone_id: int | None = None,
                gate_id: int | None = None) -> int:
    eid = db.execute(
        text(
            "INSERT INTO access_events "
            "(controller_id, event_id, apartment_id, zone_id, gate_id, direction, "
            " plate_number_normalized, decision, reason, occurred_at) "
            "VALUES (:c, :e, :a, :z, :g, 'entry', :p, 'allow', "
            " 'permanent_vehicle_allowed', now()) RETURNING id"
        ),
        {"c": controller_id, "e": event_id, "a": apartment_id, "z": zone_id,
         "g": gate_id, "p": normalized},
    ).scalar_one()
    db.commit()
    return eid


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


# ------------------------------ router wiring ------------------------------


def test_resident_router_registered() -> None:
    paths = {route.path for route in create_app().routes}
    assert "/api/v1/access/my/vehicles" in paths
    assert "/api/v1/access/my/passes" in paths
    assert "/api/v1/access/my/requests" in paths
    assert "/api/v1/access/my/events" in paths
    assert "/api/v1/access/requests" in paths
    assert "/api/v1/access/passes" in paths
    assert "/api/v1/access/passes/{pass_id}/cancel" in paths


# ------------------------------ RBAC ------------------------------


def test_my_vehicles_requires_auth_401(pg_db, pilot: PilotFixture) -> None:
    resp = TestClient(create_app()).get("/api/v1/access/my/vehicles")
    assert resp.status_code == 401


def test_my_vehicles_manager_403(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    resp = _client(uid, "manager").get("/api/v1/access/my/vehicles")
    assert resp.status_code == 403


def test_create_request_requires_auth_401(pg_db, pilot: PilotFixture) -> None:
    resp = TestClient(create_app()).post(
        "/api/v1/access/requests",
        json={"apartment_id": pilot.apartment_id, "plate_number_original": PLATE},
    )
    assert resp.status_code == 401


def test_create_pass_manager_403(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    resp = _client(uid, "manager").post(
        "/api/v1/access/passes",
        json={"apartment_id": pilot.apartment_id, "pass_type": "taxi",
              "zone_id": pilot.zone_id,
              "valid_until": (utcnow() + dt.timedelta(hours=1)).isoformat()},
    )
    assert resp.status_code == 403


def test_create_pass_applicant_pending_403(pg_db, pilot: PilotFixture) -> None:
    """applicant со статусом != approved → 403 (require_approved_roles)."""
    uid = seed_user(pg_db, roles="applicant", status="pending")
    _link_user_apartment(pg_db, uid, pilot.apartment_id)
    resp = _client(uid, "applicant", status="pending").post(
        "/api/v1/access/passes",
        json={"apartment_id": pilot.apartment_id, "pass_type": "taxi",
              "zone_id": pilot.zone_id,
              "valid_until": (utcnow() + dt.timedelta(hours=1)).isoformat()},
    )
    assert resp.status_code == 403


# ------------------------------ ownership: writes ------------------------------


def test_create_request_foreign_apartment_403(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="applicant")
    # пользователь НЕ привязан к pilot.apartment_id
    resp = _client(uid).post(
        "/api/v1/access/requests",
        json={"apartment_id": pilot.apartment_id, "plate_number_original": PLATE},
    )
    assert resp.status_code == 403


def test_create_pass_foreign_apartment_403(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="applicant")
    other_apt = _seed_apartment(pg_db)
    pg_db.commit()
    _link_user_apartment(pg_db, uid, other_apt)  # свой — другой
    resp = _client(uid).post(
        "/api/v1/access/passes",
        json={"apartment_id": pilot.apartment_id, "pass_type": "taxi",
              "zone_id": pilot.zone_id,
              "valid_until": (utcnow() + dt.timedelta(hours=1)).isoformat()},
    )
    assert resp.status_code == 403


def test_pending_link_is_not_owned_403(pg_db, pilot: PilotFixture) -> None:
    """Связь со статусом pending НЕ даёт владения (только approved)."""
    uid = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, uid, pilot.apartment_id, status="pending")
    resp = _client(uid).post(
        "/api/v1/access/requests",
        json={"apartment_id": pilot.apartment_id, "plate_number_original": PLATE},
    )
    assert resp.status_code == 403


# ------------------------------ ownership: /my isolation ------------------------------


def test_my_vehicles_isolation(pg_db, pilot: PilotFixture) -> None:
    ua = seed_user(pg_db, roles="applicant")
    ub = seed_user(pg_db, roles="applicant")
    apt_b = _seed_apartment(pg_db)
    pg_db.commit()
    _link_user_apartment(pg_db, ua, pilot.apartment_id)
    _link_user_apartment(pg_db, ub, apt_b)
    _seed_vehicle(pg_db, pilot.apartment_id, PLATE)
    _seed_vehicle(pg_db, apt_b, PLATE_B)

    body = _client(ua).get("/api/v1/access/my/vehicles").json()
    plates = {v["plate_number_normalized"] for v in body["items"]}
    assert plates == {PLATE}
    assert body["total"] == 1


def test_my_passes_isolation(pg_db, pilot: PilotFixture) -> None:
    ua = seed_user(pg_db, roles="applicant")
    ub = seed_user(pg_db, roles="applicant")
    apt_b = _seed_apartment(pg_db)
    pg_db.commit()
    _link_user_apartment(pg_db, ua, pilot.apartment_id)
    _link_user_apartment(pg_db, ub, apt_b)
    _seed_pass(pg_db, pilot.apartment_id, created_by=ua, normalized=PLATE)
    _seed_pass(pg_db, apt_b, created_by=ub, normalized=PLATE_B)

    body = _client(ua).get("/api/v1/access/my/passes").json()
    assert body["total"] == 1
    assert body["items"][0]["apartment_id"] == pilot.apartment_id


def test_my_passes_includes_created_by_self(pg_db, pilot: PilotFixture) -> None:
    """Пропуск, созданный пользователем, виден даже если квартира уже не approved."""
    uid = seed_user(pg_db, roles="applicant")
    # без user_apartments-связи, но created_by = uid
    _seed_pass(pg_db, pilot.apartment_id, created_by=uid, normalized=PLATE)
    body = _client(uid).get("/api/v1/access/my/passes").json()
    assert body["total"] == 1


def test_my_passes_status_filter(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, uid, pilot.apartment_id)
    _seed_pass(pg_db, pilot.apartment_id, created_by=uid, normalized=PLATE, status="active")
    _seed_pass(pg_db, pilot.apartment_id, created_by=uid, normalized=PLATE_B, status="revoked")
    body = _client(uid).get("/api/v1/access/my/passes?status=active").json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "active"


def test_my_requests_isolation(pg_db, pilot: PilotFixture) -> None:
    ua = seed_user(pg_db, roles="applicant")
    ub = seed_user(pg_db, roles="applicant")
    apt_b = _seed_apartment(pg_db)
    pg_db.commit()
    _link_user_apartment(pg_db, ua, pilot.apartment_id)
    _link_user_apartment(pg_db, ub, apt_b)
    _seed_request(pg_db, pilot.apartment_id, ua, plate=PLATE)
    _seed_request(pg_db, apt_b, ub, plate=PLATE_B)

    body = _client(ua).get("/api/v1/access/my/requests").json()
    assert body["total"] == 1
    assert body["items"][0]["created_by_user_id"] == ua


def test_my_events_isolation(pg_db, pilot: PilotFixture) -> None:
    ua = seed_user(pg_db, roles="applicant")
    ub = seed_user(pg_db, roles="applicant")
    apt_b = _seed_apartment(pg_db)
    pg_db.commit()
    _link_user_apartment(pg_db, ua, pilot.apartment_id)
    _link_user_apartment(pg_db, ub, apt_b)
    _seed_vehicle(pg_db, pilot.apartment_id, PLATE)
    _seed_vehicle(pg_db, apt_b, PLATE_B)
    _seed_event(pg_db, controller_id=pilot.controller_id, event_id="ev-a",
                apartment_id=pilot.apartment_id, normalized=PLATE, zone_id=pilot.zone_id,
                gate_id=pilot.gate_id)
    _seed_event(pg_db, controller_id=pilot.controller_id, event_id="ev-b",
                apartment_id=apt_b, normalized=PLATE_B, zone_id=pilot.zone_id,
                gate_id=pilot.gate_id)

    body = _client(ua).get("/api/v1/access/my/events").json()
    assert body["total"] == 1
    assert body["items"][0]["plate_number_normalized"] == PLATE


# ------------------------------ create request ------------------------------


def test_create_request_creates_pending(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, uid, pilot.apartment_id)
    resp = _client(uid).post(
        "/api/v1/access/requests",
        json={"apartment_id": pilot.apartment_id, "plate_number_original": "01 a 777 bc",
              "relation_type": "owner", "brand": "Chevrolet"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["created_by_user_id"] == uid
    assert body["apartment_id"] == pilot.apartment_id
    # номер нормализован (пробелы убраны, верхний регистр)
    assert body["plate_number_normalized"] == PLATE


def test_create_request_writes_audit(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, uid, pilot.apartment_id)
    _client(uid).post(
        "/api/v1/access/requests",
        json={"apartment_id": pilot.apartment_id, "plate_number_original": PLATE},
    )
    row = pg_db.execute(
        text(
            "SELECT actor_user_id, row_hash FROM access_audit_logs "
            "WHERE action = 'access.resident_request_create'"
        )
    ).first()
    assert row is not None
    assert row[0] == uid
    assert row[1] is not None


# ------------------------------ create pass ------------------------------


def test_create_pass_taxi_creates_active(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, uid, pilot.apartment_id)
    resp = _client(uid).post(
        "/api/v1/access/passes",
        json={"apartment_id": pilot.apartment_id, "pass_type": "taxi",
              "plate_number_original": PLATE, "zone_id": pilot.zone_id,
              "valid_until": (utcnow() + dt.timedelta(hours=2)).isoformat()},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["pass_type"] == "taxi"
    assert body["status"] == "active"
    assert body["source"] == "resident"
    assert body["created_by_user_id"] == uid
    assert body["used_entries"] == 0


def test_create_pass_guest_creates_active(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, uid, pilot.apartment_id)
    resp = _client(uid).post(
        "/api/v1/access/passes",
        json={"apartment_id": pilot.apartment_id, "pass_type": "guest",
              "zone_id": pilot.zone_id,
              "valid_until": (utcnow() + dt.timedelta(hours=2)).isoformat()},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["pass_type"] == "guest"


def test_create_pass_invalid_type_422(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, uid, pilot.apartment_id)
    resp = _client(uid).post(
        "/api/v1/access/passes",
        json={"apartment_id": pilot.apartment_id, "pass_type": "emergency",
              "zone_id": pilot.zone_id,
              "valid_until": (utcnow() + dt.timedelta(hours=2)).isoformat()},
    )
    assert resp.status_code == 422


def test_create_pass_writes_audit(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, uid, pilot.apartment_id)
    _client(uid).post(
        "/api/v1/access/passes",
        json={"apartment_id": pilot.apartment_id, "pass_type": "taxi",
              "zone_id": pilot.zone_id,
              "valid_until": (utcnow() + dt.timedelta(hours=2)).isoformat()},
    )
    action = pg_db.execute(
        text("SELECT action FROM access_audit_logs "
             "WHERE action = 'access.resident_pass_create'")
    ).scalar()
    assert action == "access.resident_pass_create"


# ------------------------------ zone resolution ------------------------------


def test_create_pass_zone_resolve_single(pg_db, pilot: PilotFixture) -> None:
    """Зона не задана; ровно одна зона обслуживает квартиру → берётся она."""
    uid = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, uid, pilot.apartment_id)
    yard = _yard_of(pg_db, pilot.apartment_id)
    _link_zone_yard(pg_db, pilot.zone_id, yard)
    resp = _client(uid).post(
        "/api/v1/access/passes",
        json={"apartment_id": pilot.apartment_id, "pass_type": "taxi",
              "valid_until": (utcnow() + dt.timedelta(hours=2)).isoformat()},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["zone_id"] == pilot.zone_id


def test_create_pass_zone_resolve_multiple_422(pg_db, pilot: PilotFixture) -> None:
    """Несколько зон обслуживают квартиру и zone_id не задан → 422."""
    from access_control.domain.territory import ParkingZone
    import uuid as _uuid

    uid = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, uid, pilot.apartment_id)
    yard = _yard_of(pg_db, pilot.apartment_id)
    _link_zone_yard(pg_db, pilot.zone_id, yard)
    zone2 = ParkingZone(code=f"z2-{_uuid.uuid4().hex[:6]}", name="Зона 2")
    pg_db.add(zone2)
    pg_db.flush()
    _link_zone_yard(pg_db, zone2.id, yard)
    resp = _client(uid).post(
        "/api/v1/access/passes",
        json={"apartment_id": pilot.apartment_id, "pass_type": "taxi",
              "valid_until": (utcnow() + dt.timedelta(hours=2)).isoformat()},
    )
    assert resp.status_code == 422


def test_create_pass_zone_unresolvable_422(pg_db, pilot: PilotFixture) -> None:
    """Ни одна зона не обслуживает квартиру и zone_id не задан → 422."""
    uid = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, uid, pilot.apartment_id)
    resp = _client(uid).post(
        "/api/v1/access/passes",
        json={"apartment_id": pilot.apartment_id, "pass_type": "taxi",
              "valid_until": (utcnow() + dt.timedelta(hours=2)).isoformat()},
    )
    assert resp.status_code == 422


# ------------------------------ cancel pass ------------------------------


def test_cancel_pass_revokes(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, uid, pilot.apartment_id)
    pid = _seed_pass(pg_db, pilot.apartment_id, created_by=uid, normalized=PLATE)
    resp = _client(uid).post(f"/api/v1/access/passes/{pid}/cancel")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "revoked"
    db_status = pg_db.execute(
        text("SELECT status FROM access_passes WHERE id = :i"), {"i": pid}
    ).scalar()
    assert db_status == "revoked"


def test_cancel_pass_idempotent(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, uid, pilot.apartment_id)
    pid = _seed_pass(pg_db, pilot.apartment_id, created_by=uid, normalized=PLATE)
    client = _client(uid)
    r1 = client.post(f"/api/v1/access/passes/{pid}/cancel")
    assert r1.status_code == 200
    r2 = client.post(f"/api/v1/access/passes/{pid}/cancel")
    assert r2.status_code == 200
    assert r2.json()["status"] == "revoked"
    # ровно одна аудит-строка отмены (повтор не пишет дубль)
    n = pg_db.execute(
        text("SELECT count(*) FROM access_audit_logs "
             "WHERE action = 'access.resident_pass_cancel' AND entity_id = :e"),
        {"e": str(pid)},
    ).scalar()
    assert n == 1


def test_cancel_foreign_pass_403(pg_db, pilot: PilotFixture) -> None:
    owner = seed_user(pg_db, roles="applicant")
    other = seed_user(pg_db, roles="applicant")
    other_apt = _seed_apartment(pg_db)
    pg_db.commit()
    _link_user_apartment(pg_db, other, other_apt)
    pid = _seed_pass(pg_db, pilot.apartment_id, created_by=owner, normalized=PLATE)
    resp = _client(other).post(f"/api/v1/access/passes/{pid}/cancel")
    assert resp.status_code == 403


def test_cancel_unknown_pass_404(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="applicant")
    resp = _client(uid).post("/api/v1/access/passes/999999/cancel")
    assert resp.status_code == 404


def test_cancel_writes_audit(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, uid, pilot.apartment_id)
    pid = _seed_pass(pg_db, pilot.apartment_id, created_by=uid, normalized=PLATE)
    _client(uid).post(f"/api/v1/access/passes/{pid}/cancel")
    row = pg_db.execute(
        text("SELECT actor_user_id, row_hash FROM access_audit_logs "
             "WHERE action = 'access.resident_pass_cancel'")
    ).first()
    assert row is not None
    assert row[0] == uid
    assert row[1] is not None


# ------------------------------ /my reads ------------------------------


def test_my_requests_status_filter(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, uid, pilot.apartment_id)
    _seed_request(pg_db, pilot.apartment_id, uid, plate=PLATE, status="pending")
    _seed_request(pg_db, pilot.apartment_id, uid, plate=PLATE_B, status="approved")
    body = _client(uid).get("/api/v1/access/my/requests?status=pending").json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "pending"


# ------------------------------ integration: pass → ANPR allow ------------------------------


def test_resident_taxi_pass_then_anpr_allows(pg_db, pilot: PilotFixture) -> None:
    """§7: созданный жителем taxi-pass → ANPR того же номера = allow temporary_pass_allowed."""
    uid = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, uid, pilot.apartment_id)
    resp = _client(uid).post(
        "/api/v1/access/passes",
        json={"apartment_id": pilot.apartment_id, "pass_type": "taxi",
              "plate_number_original": PLATE, "zone_id": pilot.zone_id,
              "valid_until": (utcnow() + dt.timedelta(hours=2)).isoformat()},
    )
    assert resp.status_code == 201, resp.text

    result = _ingest(pg_db, pilot, plate=PLATE, event_id="ev-resident-taxi-1")
    assert result.decision == "allow"
    assert result.reason == "temporary_pass_allowed"
