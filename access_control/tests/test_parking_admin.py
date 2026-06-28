"""Ф?: ADMIN-эндпоинты управления парковкой — этап 2 (§5, §6.2, §7, §10.3).

Поверх реестра оборудования (test_equipment_api) добавляет управление:

* ЗОНА — тип/ёмкость: ``parking_type`` (assigned|shared) + ``capacity`` в
  ZoneRow/ZoneCreate/ZonePatch (manager/system_admin, §6.2 «настройка зон»);
* МЕСТА (``parking_spots``): список/создание (409 на дубль (zone_id, code))/patch
  статуса;
* ЗАКРЕПЛЕНИЯ (``parking_spot_assignments``): список/создание (owned бессрочно /
  rented со сроком)/patch (revoke, продление).

RBAC: manager + system_admin → 200/201; applicant/executor/inspector/
security_operator → 403; без auth → 401. Каждое изменение пишет append-only
``access_audit_logs`` (§9.7). Удаления нет — деактивация статусом.

Интеграция (§7): assigned-зона + место + закрепление квартиры → ANPR авто этой
квартиры даёт allow ``assigned_spot_allowed``; revoke/expiry → ``spot_not_assigned``/
``spot_rental_expired`` (срок enforce'ится живо Decision Engine, без воркера).
Учёт заездов (§10.3): occupancy-эндпоинт считает разрешённые въезды. PostgreSQL-only.
"""
from __future__ import annotations

import datetime as dt
import json
import types
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.services.decision_engine import AnprDecisionInput, decide
from access_control.tests.conftest import seed_permanent_vehicle, seed_user, utcnow
from uk_management_bot.api.dependencies import get_current_user


# ------------------------------ helpers ------------------------------


def _fake_user(uid: int, role: str, status: str = "approved"):
    return lambda: types.SimpleNamespace(
        id=uid, roles=json.dumps([role]), active_role=role, status=status
    )


def _client(uid: int, role: str, status: str = "approved") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, role, status)
    return TestClient(app)


def _u(db, role: str) -> int:
    return seed_user(db, roles=role)


def _mgr(db) -> TestClient:
    return _client(_u(db, "manager"), "manager")


def _create_zone(client: TestClient, **kw) -> dict:
    body = {"code": f"z-{uuid.uuid4().hex[:6]}", "name": "Зона"}
    body.update(kw)
    resp = client.post("/api/v1/access/admin/zones", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_spot(client: TestClient, zone_id: int, **kw) -> dict:
    body = {"zone_id": zone_id, "code": f"sp-{uuid.uuid4().hex[:6]}"}
    body.update(kw)
    resp = client.post("/api/v1/access/admin/spots", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _decide_input(pilot, normalized, *, captured_at=None):
    return AnprDecisionInput(
        controller_id=pilot.controller_id,
        zone_id=pilot.zone_id,
        gate_id=pilot.gate_id,
        camera_id=pilot.camera_id,
        plate_number_normalized=normalized,
        recognition_key=normalized,
        direction="entry",
        confidence=0.95,
        captured_at=captured_at or utcnow(),
    )


# ------------------------------ router wiring ------------------------------


def test_parking_admin_routes_registered() -> None:
    paths = {route.path for route in create_app().routes}
    for p in (
        "/api/v1/access/admin/spots",
        "/api/v1/access/admin/spots/{spot_id}",
        "/api/v1/access/admin/spot-assignments",
        "/api/v1/access/admin/spot-assignments/{assignment_id}",
        "/api/v1/access/admin/zones/{zone_id}/occupancy",
    ):
        assert p in paths, f"маршрут не зарегистрирован: {p}"


# =========================== ЗОНА: тип/ёмкость ===========================


def test_zone_create_with_parking_type_and_capacity(pg_db) -> None:
    c = _mgr(pg_db)
    z = _create_zone(c, parking_type="assigned", capacity=50)
    assert z["parking_type"] == "assigned"
    assert z["capacity"] == 50


def test_zone_default_parking_type_shared(pg_db) -> None:
    c = _mgr(pg_db)
    z = _create_zone(c)
    assert z["parking_type"] == "shared"
    assert z["capacity"] is None


def test_zone_patch_parking_type_and_capacity(pg_db) -> None:
    c = _mgr(pg_db)
    z = _create_zone(c)
    resp = c.patch(
        f"/api/v1/access/admin/zones/{z['id']}",
        json={"parking_type": "assigned", "capacity": 12},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["parking_type"] == "assigned"
    assert body["capacity"] == 12


def test_zone_bad_parking_type_422(pg_db) -> None:
    c = _mgr(pg_db)
    resp = c.post(
        "/api/v1/access/admin/zones",
        json={"code": f"z-{uuid.uuid4().hex[:6]}", "name": "X", "parking_type": "nope"},
    )
    assert resp.status_code == 422


def test_zone_negative_capacity_422(pg_db) -> None:
    c = _mgr(pg_db)
    resp = c.post(
        "/api/v1/access/admin/zones",
        json={"code": f"z-{uuid.uuid4().hex[:6]}", "name": "X", "capacity": -1},
    )
    assert resp.status_code == 422


# =============================== МЕСТА: RBAC ===============================


def test_spots_requires_auth_401(pg_db) -> None:
    assert TestClient(create_app()).get("/api/v1/access/admin/spots").status_code == 401


def test_spots_manager_ok(pg_db) -> None:
    assert _mgr(pg_db).get("/api/v1/access/admin/spots").status_code == 200


def test_spots_system_admin_ok(pg_db) -> None:
    uid = _u(pg_db, "system_admin")
    assert (
        _client(uid, "system_admin").get("/api/v1/access/admin/spots").status_code == 200
    )


def test_spots_applicant_403(pg_db) -> None:
    uid = _u(pg_db, "applicant")
    assert _client(uid, "applicant").get("/api/v1/access/admin/spots").status_code == 403


def test_spots_security_operator_403(pg_db) -> None:
    uid = _u(pg_db, "security_operator")
    assert (
        _client(uid, "security_operator").get("/api/v1/access/admin/spots").status_code
        == 403
    )


# =============================== МЕСТА: CRUD ===============================


def test_spot_create_and_list_envelope(pg_db) -> None:
    c = _mgr(pg_db)
    z = _create_zone(c)
    sp = _create_spot(c, z["id"], code="A-01")
    assert sp["zone_id"] == z["id"]
    assert sp["code"] == "A-01"
    assert sp["status"] == "active"

    page = c.get(f"/api/v1/access/admin/spots?zone_id={z['id']}").json()
    assert set(page.keys()) >= {"items", "total", "limit", "offset"}
    assert page["total"] >= 1
    assert any(it["id"] == sp["id"] for it in page["items"])


def test_spot_list_filter_by_status(pg_db) -> None:
    c = _mgr(pg_db)
    z = _create_zone(c)
    active = _create_spot(c, z["id"])
    inactive = _create_spot(c, z["id"])
    c.patch(f"/api/v1/access/admin/spots/{inactive['id']}", json={"status": "inactive"})

    page = c.get(
        f"/api/v1/access/admin/spots?zone_id={z['id']}&status=active"
    ).json()
    ids = {it["id"] for it in page["items"]}
    assert active["id"] in ids
    assert inactive["id"] not in ids


def test_spot_duplicate_code_409(pg_db) -> None:
    c = _mgr(pg_db)
    z = _create_zone(c)
    _create_spot(c, z["id"], code="DUP-1")
    dup = c.post(
        "/api/v1/access/admin/spots", json={"zone_id": z["id"], "code": "DUP-1"}
    )
    assert dup.status_code == 409


def test_spot_same_code_different_zone_ok(pg_db) -> None:
    c = _mgr(pg_db)
    z1 = _create_zone(c)
    z2 = _create_zone(c)
    _create_spot(c, z1["id"], code="SHARED-CODE")
    ok = c.post(
        "/api/v1/access/admin/spots", json={"zone_id": z2["id"], "code": "SHARED-CODE"}
    )
    assert ok.status_code == 201, ok.text


def test_spot_bad_zone_id_422(pg_db) -> None:
    c = _mgr(pg_db)
    resp = c.post(
        "/api/v1/access/admin/spots", json={"zone_id": 999999, "code": "X"}
    )
    assert resp.status_code == 422


def test_spot_patch_status_and_code(pg_db) -> None:
    c = _mgr(pg_db)
    z = _create_zone(c)
    sp = _create_spot(c, z["id"])
    resp = c.patch(
        f"/api/v1/access/admin/spots/{sp['id']}",
        json={"status": "archived", "code": "renamed"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "archived"
    assert resp.json()["code"] == "renamed"


def test_spot_patch_bad_status_422(pg_db) -> None:
    c = _mgr(pg_db)
    z = _create_zone(c)
    sp = _create_spot(c, z["id"])
    resp = c.patch(
        f"/api/v1/access/admin/spots/{sp['id']}", json={"status": "deleted"}
    )
    assert resp.status_code == 422


def test_spot_patch_unknown_404(pg_db) -> None:
    c = _mgr(pg_db)
    resp = c.patch("/api/v1/access/admin/spots/999999", json={"status": "inactive"})
    assert resp.status_code == 404


def test_spot_create_writes_audit(pg_db) -> None:
    c = _mgr(pg_db)
    z = _create_zone(c)
    sp = _create_spot(c, z["id"])
    row = pg_db.execute(
        text(
            "SELECT action, row_hash FROM access_audit_logs "
            "WHERE action = 'access.spot_create' AND entity_id = :e"
        ),
        {"e": str(sp["id"])},
    ).first()
    assert row is not None
    assert row[1] is not None


# =========================== ЗАКРЕПЛЕНИЯ: RBAC ===========================


def test_spot_assignments_requires_auth_401(pg_db) -> None:
    assert (
        TestClient(create_app())
        .get("/api/v1/access/admin/spot-assignments")
        .status_code
        == 401
    )


def test_spot_assignments_manager_ok(pg_db) -> None:
    assert _mgr(pg_db).get("/api/v1/access/admin/spot-assignments").status_code == 200


def test_spot_assignments_executor_403(pg_db) -> None:
    uid = _u(pg_db, "executor")
    assert (
        _client(uid, "executor")
        .get("/api/v1/access/admin/spot-assignments")
        .status_code
        == 403
    )


# =========================== ЗАКРЕПЛЕНИЯ: CRUD ===========================


def test_assignment_create_owned(pg_db, pilot) -> None:
    c = _mgr(pg_db)
    sp = _create_spot(c, pilot.zone_id)
    resp = c.post(
        "/api/v1/access/admin/spot-assignments",
        json={
            "spot_id": sp["id"],
            "apartment_id": pilot.apartment_id,
            "ownership_type": "owned",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["ownership_type"] == "owned"
    assert body["status"] == "active"
    assert body["valid_until"] is None
    assert body["approved_by_user_id"] is not None
    assert body["approved_at"] is not None


def test_assignment_create_rented_with_term(pg_db, pilot) -> None:
    c = _mgr(pg_db)
    sp = _create_spot(c, pilot.zone_id)
    until = (utcnow() + dt.timedelta(days=30)).isoformat()
    resp = c.post(
        "/api/v1/access/admin/spot-assignments",
        json={
            "spot_id": sp["id"],
            "apartment_id": pilot.apartment_id,
            "ownership_type": "rented",
            "valid_until": until,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["ownership_type"] == "rented"


def test_assignment_rented_without_valid_until_422(pg_db, pilot) -> None:
    c = _mgr(pg_db)
    sp = _create_spot(c, pilot.zone_id)
    resp = c.post(
        "/api/v1/access/admin/spot-assignments",
        json={
            "spot_id": sp["id"],
            "apartment_id": pilot.apartment_id,
            "ownership_type": "rented",
        },
    )
    assert resp.status_code == 422


def test_assignment_bad_spot_id_422(pg_db, pilot) -> None:
    c = _mgr(pg_db)
    resp = c.post(
        "/api/v1/access/admin/spot-assignments",
        json={
            "spot_id": 999999,
            "apartment_id": pilot.apartment_id,
            "ownership_type": "owned",
        },
    )
    assert resp.status_code == 422


def test_assignment_bad_apartment_id_422(pg_db, pilot) -> None:
    c = _mgr(pg_db)
    sp = _create_spot(c, pilot.zone_id)
    resp = c.post(
        "/api/v1/access/admin/spot-assignments",
        json={"spot_id": sp["id"], "apartment_id": 999999, "ownership_type": "owned"},
    )
    assert resp.status_code == 422


def test_assignment_list_filters(pg_db, pilot) -> None:
    c = _mgr(pg_db)
    sp = _create_spot(c, pilot.zone_id)
    created = c.post(
        "/api/v1/access/admin/spot-assignments",
        json={
            "spot_id": sp["id"],
            "apartment_id": pilot.apartment_id,
            "ownership_type": "owned",
        },
    ).json()
    page = c.get(
        f"/api/v1/access/admin/spot-assignments?spot_id={sp['id']}&status=active"
    ).json()
    assert set(page.keys()) >= {"items", "total", "limit", "offset"}
    assert any(it["id"] == created["id"] for it in page["items"])

    by_apt = c.get(
        f"/api/v1/access/admin/spot-assignments?apartment_id={pilot.apartment_id}"
    ).json()
    assert by_apt["total"] >= 1


def test_assignment_patch_revoke(pg_db, pilot) -> None:
    c = _mgr(pg_db)
    sp = _create_spot(c, pilot.zone_id)
    a = c.post(
        "/api/v1/access/admin/spot-assignments",
        json={
            "spot_id": sp["id"],
            "apartment_id": pilot.apartment_id,
            "ownership_type": "owned",
        },
    ).json()
    resp = c.patch(
        f"/api/v1/access/admin/spot-assignments/{a['id']}", json={"status": "revoked"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "revoked"


def test_assignment_patch_extend_valid_until(pg_db, pilot) -> None:
    c = _mgr(pg_db)
    sp = _create_spot(c, pilot.zone_id)
    until = (utcnow() + dt.timedelta(days=10)).isoformat()
    a = c.post(
        "/api/v1/access/admin/spot-assignments",
        json={
            "spot_id": sp["id"],
            "apartment_id": pilot.apartment_id,
            "ownership_type": "rented",
            "valid_until": until,
        },
    ).json()
    new_until = (utcnow() + dt.timedelta(days=60)).isoformat()
    resp = c.patch(
        f"/api/v1/access/admin/spot-assignments/{a['id']}",
        json={"valid_until": new_until},
    )
    assert resp.status_code == 200, resp.text


def test_assignment_patch_unknown_404(pg_db) -> None:
    c = _mgr(pg_db)
    resp = c.patch(
        "/api/v1/access/admin/spot-assignments/999999", json={"status": "revoked"}
    )
    assert resp.status_code == 404


def test_assignment_create_writes_audit(pg_db, pilot) -> None:
    c = _mgr(pg_db)
    sp = _create_spot(c, pilot.zone_id)
    a = c.post(
        "/api/v1/access/admin/spot-assignments",
        json={
            "spot_id": sp["id"],
            "apartment_id": pilot.apartment_id,
            "ownership_type": "owned",
        },
    ).json()
    row = pg_db.execute(
        text(
            "SELECT row_hash FROM access_audit_logs "
            "WHERE action = 'access.spot_assignment_create' AND entity_id = :e"
        ),
        {"e": str(a["id"])},
    ).first()
    assert row is not None and row[0] is not None


# =================== ИНТЕГРАЦИЯ: assigned → Decision Engine ===================


def test_assigned_assignment_allows_apartment_vehicle(pg_db, pilot) -> None:
    """assigned-зона + место + закрепление квартиры → allow assigned_spot_allowed."""
    c = _mgr(pg_db)
    c.patch(
        f"/api/v1/access/admin/zones/{pilot.zone_id}",
        json={"parking_type": "assigned"},
    )
    sp = _create_spot(c, pilot.zone_id)
    vid = seed_permanent_vehicle(pg_db, pilot, normalized="01ADM01A", with_rule=False)
    a = c.post(
        "/api/v1/access/admin/spot-assignments",
        json={
            "spot_id": sp["id"],
            "apartment_id": pilot.apartment_id,
            "ownership_type": "owned",
        },
    ).json()

    res = decide(pg_db, _decide_input(pilot, "01ADM01A"))
    assert res.decision == "allow"
    assert res.reason == "assigned_spot_allowed"
    assert res.matched_vehicle_id == vid

    # revoke → закрепления нет → spot_not_assigned.
    c.patch(
        f"/api/v1/access/admin/spot-assignments/{a['id']}", json={"status": "revoked"}
    )
    res2 = decide(pg_db, _decide_input(pilot, "01ADM01A"))
    assert res2.decision == "deny"
    assert res2.reason == "spot_not_assigned"


def test_assigned_rented_expiry_denies(pg_db, pilot) -> None:
    """rented-закрепление с истёкшим valid_until → spot_rental_expired (живой enforce)."""
    c = _mgr(pg_db)
    c.patch(
        f"/api/v1/access/admin/zones/{pilot.zone_id}",
        json={"parking_type": "assigned"},
    )
    sp = _create_spot(c, pilot.zone_id)
    seed_permanent_vehicle(pg_db, pilot, normalized="01ADM02A", with_rule=False)
    past = utcnow() - dt.timedelta(days=2)
    c.post(
        "/api/v1/access/admin/spot-assignments",
        json={
            "spot_id": sp["id"],
            "apartment_id": pilot.apartment_id,
            "ownership_type": "rented",
            "valid_from": (past - dt.timedelta(days=1)).isoformat(),
            "valid_until": past.isoformat(),
        },
    )
    res = decide(pg_db, _decide_input(pilot, "01ADM02A"))
    assert res.decision == "deny"
    assert res.reason == "spot_rental_expired"


# ============================ ЗАНЯТОСТЬ ЗОНЫ ============================


def _insert_allow_entry(db, pilot) -> None:
    db.execute(
        text(
            "INSERT INTO access_events "
            "(controller_id, event_id, zone_id, gate_id, direction, decision, "
            " reason, occurred_at) "
            "VALUES (:c, :e, :z, :g, 'entry', 'allow', 'shared_access_allowed', now())"
        ),
        {
            "c": pilot.controller_id,
            "e": f"occ-{uuid.uuid4().hex[:10]}",
            "z": pilot.zone_id,
            "g": pilot.gate_id,
        },
    )
    db.commit()


def test_zone_occupancy_endpoint(pg_db, pilot) -> None:
    c = _mgr(pg_db)
    # capacity для UI shared-зоны.
    c.patch(f"/api/v1/access/admin/zones/{pilot.zone_id}", json={"capacity": 100})
    for _ in range(2):
        _insert_allow_entry(pg_db, pilot)
    resp = c.get(f"/api/v1/access/admin/zones/{pilot.zone_id}/occupancy")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["entries"] == 2
    assert body["exits"] == 0
    assert body["occupancy"] == 2
    assert body["capacity"] == 100


def test_zone_occupancy_unknown_zone_404(pg_db) -> None:
    c = _mgr(pg_db)
    resp = c.get("/api/v1/access/admin/zones/999999/occupancy")
    assert resp.status_code == 404


def test_zone_occupancy_security_operator_403(pg_db, pilot) -> None:
    uid = _u(pg_db, "security_operator")
    resp = _client(uid, "security_operator").get(
        f"/api/v1/access/admin/zones/{pilot.zone_id}/occupancy"
    )
    assert resp.status_code == 403
