"""Детали и редактирование базы доступа (экран менеджера, §6.2/§13.2). PG-only.

Покрывает доработку «База доступа»:

* ``GET /api/v1/access/requests/{id}`` — деталь заявки + заявитель/адрес/зоны/авто;
* ``GET /api/v1/access/passes/{id}`` — деталь пропуска + заявитель/адрес/зона;
* ``GET /api/v1/access/vehicles/{id}`` — карточка + apartment_details (адрес/жители/зоны);
* ``PATCH /api/v1/access/vehicles/{id}`` — правка атрибутов/номера/привязки владельца;
* ``PATCH /api/v1/access/passes/{id}`` — продление/лимит/номер/отзыв.

RBAC (§6.2): manager/system_admin — да; security_operator — 403 на /vehicles и
/requests (но видит /passes). Без auth — 401.
"""
from __future__ import annotations

import datetime as dt
import types

from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.tests.conftest import (
    PilotFixture,
    _seed_apartment,
    seed_user,
    utcnow,
)
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


def _apartment_yard(db, apartment_id: int) -> int:
    return db.execute(
        text(
            "SELECT b.yard_id FROM apartments a JOIN buildings b ON b.id = a.building_id "
            "WHERE a.id = :id"
        ),
        {"id": apartment_id},
    ).scalar()


def _map_zone_yard(db, zone_id: int, yard_id: int) -> None:
    db.execute(
        text(
            "INSERT INTO parking_zone_yards (zone_id, yard_id) VALUES (:z, :y) "
            "ON CONFLICT (zone_id, yard_id) DO NOTHING"
        ),
        {"z": zone_id, "y": yard_id},
    )
    db.commit()


# ------------------------------ GET /requests/{id} ------------------------------


def test_request_detail_enriched(pg_db, pilot: PilotFixture) -> None:
    creator = seed_user(pg_db, roles="applicant")
    rid = _seed_request(pg_db, pilot, creator_id=creator)
    _map_zone_yard(pg_db, pilot.zone_id, _apartment_yard(pg_db, pilot.apartment_id))

    uid = seed_user(pg_db, roles="manager")
    resp = _client(uid, "manager").get(f"/api/v1/access/requests/{rid}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["request"]["id"] == rid
    assert body["applicant"]["user_id"] == creator
    assert body["address"]["apartment_id"] == pilot.apartment_id
    assert body["address"]["building_address"] is not None
    assert any(z["id"] == pilot.zone_id for z in body["serving_zones"])


def test_request_detail_unknown_404(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    resp = _client(uid, "manager").get("/api/v1/access/requests/999999")
    assert resp.status_code == 404


def test_request_detail_operator_403(pg_db, pilot: PilotFixture) -> None:
    creator = seed_user(pg_db, roles="applicant")
    rid = _seed_request(pg_db, pilot, creator_id=creator)
    uid = seed_user(pg_db, roles="security_operator")
    resp = _client(uid, "security_operator").get(f"/api/v1/access/requests/{rid}")
    assert resp.status_code == 403


# ------------------------------ GET /passes/{id} ------------------------------


def test_pass_detail_enriched(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    created = client.post(
        "/api/v1/access/passes/taxi",
        json={"apartment_id": pilot.apartment_id, "zone_id": pilot.zone_id,
              "plate_number_original": PLATE,
              "valid_until": (utcnow() + dt.timedelta(hours=2)).isoformat()},
    ).json()
    pid = created["id"]

    resp = client.get(f"/api/v1/access/passes/{pid}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pass"]["id"] == pid  # serialization_alias
    assert body["applicant"]["user_id"] == uid
    assert body["address"]["apartment_id"] == pilot.apartment_id
    assert body["zone"]["id"] == pilot.zone_id


def test_pass_detail_operator_allowed(pg_db, pilot: PilotFixture) -> None:
    """Оператор охраны видит /passes (EVENTS_PASSES_ROLES)."""
    mgr = seed_user(pg_db, roles="manager")
    pid = _client(mgr, "manager").post(
        "/api/v1/access/passes/taxi",
        json={"apartment_id": pilot.apartment_id, "zone_id": pilot.zone_id,
              "valid_until": (utcnow() + dt.timedelta(hours=2)).isoformat()},
    ).json()["id"]
    op = seed_user(pg_db, roles="security_operator")
    resp = _client(op, "security_operator").get(f"/api/v1/access/passes/{pid}")
    assert resp.status_code == 200


def test_pass_detail_unknown_404(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    assert _client(uid, "manager").get(
        "/api/v1/access/passes/999999"
    ).status_code == 404


# ------------------------------ GET /vehicles/{id} ------------------------------


def test_vehicle_detail_apartment_details(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    vid = client.post(
        "/api/v1/access/vehicles",
        json={"plate_number_original": PLATE, "apartment_id": pilot.apartment_id,
              "relation_type": "owner"},
    ).json()["id"]
    _map_zone_yard(pg_db, pilot.zone_id, _apartment_yard(pg_db, pilot.apartment_id))

    resp = client.get(f"/api/v1/access/vehicles/{vid}")
    assert resp.status_code == 200, resp.text
    details = resp.json()["apartment_details"]
    assert len(details) == 1
    d = details[0]
    assert d["apartment_id"] == pilot.apartment_id
    assert d["relation_type"] == "owner"
    assert d["address"]["apartment_id"] == pilot.apartment_id
    assert any(z["id"] == pilot.zone_id for z in d["zones"])


# ------------------------------ PATCH /vehicles/{id} ------------------------------


def _make_vehicle(client, *, plate=PLATE, apartment_id=None, relation="owner") -> int:
    body = {"plate_number_original": plate}
    if apartment_id is not None:
        body |= {"apartment_id": apartment_id, "relation_type": relation}
    return client.post("/api/v1/access/vehicles", json=body).json()["id"]


def test_patch_vehicle_attributes(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    vid = _make_vehicle(client)
    resp = client.patch(
        f"/api/v1/access/vehicles/{vid}",
        json={"brand": "Kia", "model": "K5", "color": "чёрный",
              "vehicle_class": "sedan"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["brand"] == "Kia"
    assert body["model"] == "K5"
    assert body["color"] == "чёрный"
    assert body["vehicle_class"] == "sedan"


def test_patch_vehicle_plate_renormalizes(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    vid = _make_vehicle(client)
    resp = client.patch(
        f"/api/v1/access/vehicles/{vid}",
        json={"plate_number_original": "01x999yz"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["plate_number_normalized"] == "01X999YZ"


def test_patch_vehicle_plate_duplicate_409(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    _make_vehicle(client, plate="01A111AA")
    vid2 = _make_vehicle(client, plate="01B222BB")
    resp = client.patch(
        f"/api/v1/access/vehicles/{vid2}",
        json={"plate_number_original": "01A111AA"},
    )
    assert resp.status_code == 409


def test_patch_vehicle_relink_owner(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    apt2 = _seed_apartment(pg_db)
    pg_db.commit()
    vid = _make_vehicle(client, apartment_id=pilot.apartment_id, relation="owner")

    resp = client.patch(
        f"/api/v1/access/vehicles/{vid}",
        json={"apartment_id": apt2, "relation_type": "tenant"},
    )
    assert resp.status_code == 200, resp.text

    detail = client.get(f"/api/v1/access/vehicles/{vid}").json()
    active = [d for d in detail["apartment_details"] if d["status"] == "active"]
    assert len(active) == 1
    assert active[0]["apartment_id"] == apt2
    assert active[0]["relation_type"] == "tenant"


def test_patch_vehicle_unknown_404(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    assert _client(uid, "manager").patch(
        "/api/v1/access/vehicles/999999", json={"color": "x"}
    ).status_code == 404


def test_patch_vehicle_operator_403(pg_db, pilot: PilotFixture) -> None:
    mgr = seed_user(pg_db, roles="manager")
    vid = _make_vehicle(_client(mgr, "manager"))
    op = seed_user(pg_db, roles="security_operator")
    resp = _client(op, "security_operator").patch(
        f"/api/v1/access/vehicles/{vid}", json={"color": "x"}
    )
    assert resp.status_code == 403


# ------------------------------ PATCH /passes/{id} ------------------------------


def _make_pass(client, pilot: PilotFixture, *, hours: int = 2) -> int:
    return client.post(
        "/api/v1/access/passes/taxi",
        json={"apartment_id": pilot.apartment_id, "zone_id": pilot.zone_id,
              "valid_until": (utcnow() + dt.timedelta(hours=hours)).isoformat()},
    ).json()["id"]


def test_patch_pass_extend_and_limit(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    pid = _make_pass(client, pilot)
    new_until = (utcnow() + dt.timedelta(days=2)).isoformat()
    resp = client.patch(
        f"/api/v1/access/passes/{pid}",
        json={"valid_until": new_until, "max_entries": 5,
              "plate_number_original": "01T999AA"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["max_entries"] == 5
    assert body["plate_number_normalized"] == "01T999AA"


def test_patch_pass_revoke(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    pid = _make_pass(client, pilot)
    resp = client.patch(
        f"/api/v1/access/passes/{pid}", json={"status": "revoked"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "revoked"


def test_patch_pass_unknown_404(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    assert _client(uid, "manager").patch(
        "/api/v1/access/passes/999999", json={"status": "revoked"}
    ).status_code == 404


def test_patch_pass_applicant_403(pg_db, pilot: PilotFixture) -> None:
    mgr = seed_user(pg_db, roles="manager")
    pid = _make_pass(_client(mgr, "manager"), pilot)
    app_uid = seed_user(pg_db, roles="applicant")
    resp = _client(app_uid, "applicant").patch(
        f"/api/v1/access/passes/{pid}", json={"status": "revoked"}
    )
    assert resp.status_code == 403


# ------------------------------ router wiring ------------------------------


def test_detail_routes_registered() -> None:
    paths = {route.path for route in create_app().routes}
    assert "/api/v1/access/requests/{request_id}" in paths
    assert "/api/v1/access/passes/{pass_id}" in paths
    assert "/api/v1/access/vehicles/{vehicle_id}" in paths
