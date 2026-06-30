"""Зоно-скоупинг базы доступа (чекбоксы зон, §6.2/§13.2). PG-only.

Покрывает доработку «зоны парковки чекбоксами»:

* ``PATCH /api/v1/access/vehicles/{id}`` c ``zone_ids`` — синхронизация явных
  access_rules авто (добавление/деактивация), отражение в ``rule_zones``;
* ``POST  /api/v1/access/requests/{id}/review`` c ``zone_ids`` — несколько правил;
* ``PATCH /api/v1/access/passes/{id}`` c ``zone_id`` — смена зоны пропуска;
* ``POST  /api/v1/access/passes/taxi`` без ``zone_id`` — дефолт по адресу жителя;
* ``GET   /api/v1/access/apartments/{id}/serving-zones`` — кандидаты-чекбоксы;
* ``_resolve_zone_id`` (бот): несколько зон адреса → первая (дефолт), не ошибка.
"""
from __future__ import annotations

import datetime as dt
import json
import types
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.services.resident import _resolve_zone_id
from access_control.tests.conftest import PilotFixture, seed_user, utcnow
from uk_management_bot.api.dependencies import get_current_user

PLATE = "01A123BC"


def _fake_user(uid: int, role: str, status: str = "approved"):
    return lambda: types.SimpleNamespace(
        id=uid, roles=json.dumps([role]), active_role=role, status=status
    )


def _client(uid: int, role: str, status: str = "approved") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, role, status)
    return TestClient(app)


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


def _seed_zone(db, name: str = "Зона тест") -> int:
    zid = db.execute(
        text("INSERT INTO parking_zones (code, name) VALUES (:c, :n) RETURNING id"),
        {"c": f"z-{uuid.uuid4().hex[:6]}", "n": name},
    ).scalar()
    db.commit()
    return zid


def _active_rule_zones(db, vehicle_id: int) -> set[int]:
    rows = db.execute(
        text(
            "SELECT zone_id FROM access_rules "
            "WHERE vehicle_id = :v AND is_active = true"
        ),
        {"v": vehicle_id},
    ).scalars()
    return set(rows)


def _make_vehicle(client, *, apartment_id: int) -> int:
    return client.post(
        "/api/v1/access/vehicles",
        json={
            "plate_number_original": PLATE,
            "apartment_id": apartment_id,
            "relation_type": "owner",
        },
    ).json()["id"]


# ------------------------- PATCH /vehicles/{id} zone_ids -------------------------


def test_patch_vehicle_zone_ids_sync(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    vid = _make_vehicle(client, apartment_id=pilot.apartment_id)
    z2 = _seed_zone(pg_db, "Зона 2")

    # Назначаем две зоны чекбоксами → два активных правила.
    resp = client.patch(
        f"/api/v1/access/vehicles/{vid}",
        json={"zone_ids": [pilot.zone_id, z2]},
    )
    assert resp.status_code == 200, resp.text
    assert _active_rule_zones(pg_db, vid) == {pilot.zone_id, z2}

    # rule_zones отражён в детали авто.
    detail = client.get(f"/api/v1/access/vehicles/{vid}").json()
    assert {z["id"] for z in detail["rule_zones"]} == {pilot.zone_id, z2}

    # Снимаем одну зону → правило деактивируется, остаётся одно.
    resp = client.patch(
        f"/api/v1/access/vehicles/{vid}", json={"zone_ids": [z2]}
    )
    assert resp.status_code == 200, resp.text
    assert _active_rule_zones(pg_db, vid) == {z2}


def test_patch_vehicle_zone_ids_empty_clears(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    vid = _make_vehicle(client, apartment_id=pilot.apartment_id)
    client.patch(f"/api/v1/access/vehicles/{vid}", json={"zone_ids": [pilot.zone_id]})
    assert _active_rule_zones(pg_db, vid) == {pilot.zone_id}

    # Пустой список — снять все зоны.
    resp = client.patch(f"/api/v1/access/vehicles/{vid}", json={"zone_ids": []})
    assert resp.status_code == 200, resp.text
    assert _active_rule_zones(pg_db, vid) == set()


def test_patch_vehicle_zone_ids_revives_rule(pg_db, pilot: PilotFixture) -> None:
    """Повторное включение зоны реактивирует правило, без накопления дублей."""
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    vid = _make_vehicle(client, apartment_id=pilot.apartment_id)
    client.patch(f"/api/v1/access/vehicles/{vid}", json={"zone_ids": [pilot.zone_id]})
    client.patch(f"/api/v1/access/vehicles/{vid}", json={"zone_ids": []})
    client.patch(f"/api/v1/access/vehicles/{vid}", json={"zone_ids": [pilot.zone_id]})

    total = pg_db.execute(
        text("SELECT count(*) FROM access_rules WHERE vehicle_id = :v"),
        {"v": vid},
    ).scalar()
    assert total == 1  # реактивирована та же строка
    assert _active_rule_zones(pg_db, vid) == {pilot.zone_id}


# --------------------- POST /requests/{id}/review zone_ids ----------------------


def _seed_request(db, pilot: PilotFixture, creator_id: int) -> int:
    rid = db.execute(
        text(
            "INSERT INTO resident_access_requests "
            "(apartment_id, created_by_user_id, plate_number_original, "
            " plate_number_normalized, relation_type, status) "
            "VALUES (:a, :c, :po, :pn, 'owner', 'pending') RETURNING id"
        ),
        {"a": pilot.apartment_id, "c": creator_id, "po": PLATE, "pn": PLATE},
    ).scalar()
    db.commit()
    return rid


def test_review_approve_multi_zone(pg_db, pilot: PilotFixture) -> None:
    creator = seed_user(pg_db, roles="applicant")
    rid = _seed_request(pg_db, pilot, creator)
    z2 = _seed_zone(pg_db, "Зона 2")

    uid = seed_user(pg_db, roles="manager")
    resp = _client(uid, "manager").post(
        f"/api/v1/access/requests/{rid}/review",
        json={"action": "approve", "zone_ids": [pilot.zone_id, z2]},
    )
    assert resp.status_code == 200, resp.text
    vid = resp.json()["vehicle_id"]
    assert _active_rule_zones(pg_db, vid) == {pilot.zone_id, z2}


def test_review_approve_back_compat_zone_id(pg_db, pilot: PilotFixture) -> None:
    creator = seed_user(pg_db, roles="applicant")
    rid = _seed_request(pg_db, pilot, creator)
    uid = seed_user(pg_db, roles="manager")
    resp = _client(uid, "manager").post(
        f"/api/v1/access/requests/{rid}/review",
        json={"action": "approve", "zone_id": pilot.zone_id},
    )
    assert resp.status_code == 200, resp.text
    vid = resp.json()["vehicle_id"]
    assert _active_rule_zones(pg_db, vid) == {pilot.zone_id}


# ------------------------- PATCH /passes/{id} zone_id ---------------------------


def _make_taxi(client, *, apartment_id: int, zone_id: int | None = None) -> dict:
    body = {
        "apartment_id": apartment_id,
        "valid_until": (utcnow() + dt.timedelta(hours=2)).isoformat(),
    }
    if zone_id is not None:
        body["zone_id"] = zone_id
    return client.post("/api/v1/access/passes/taxi", json=body).json()


def test_patch_pass_zone(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    pid = _make_taxi(client, apartment_id=pilot.apartment_id, zone_id=pilot.zone_id)["id"]
    z2 = _seed_zone(pg_db, "Зона 2")

    resp = client.patch(f"/api/v1/access/passes/{pid}", json={"zone_id": z2})
    assert resp.status_code == 200, resp.text
    assert resp.json()["zone_id"] == z2


def test_pass_detail_serving_zones(pg_db, pilot: PilotFixture) -> None:
    _map_zone_yard(pg_db, pilot.zone_id, _apartment_yard(pg_db, pilot.apartment_id))
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    pid = _make_taxi(client, apartment_id=pilot.apartment_id, zone_id=pilot.zone_id)["id"]

    body = client.get(f"/api/v1/access/passes/{pid}").json()
    assert any(z["id"] == pilot.zone_id for z in body["serving_zones"])


# --------------------- POST /passes/taxi default zone from address --------------


def test_taxi_pass_default_zone_from_address(pg_db, pilot: PilotFixture) -> None:
    _map_zone_yard(pg_db, pilot.zone_id, _apartment_yard(pg_db, pilot.apartment_id))
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    created = _make_taxi(client, apartment_id=pilot.apartment_id)  # без zone_id
    assert created["zone_id"] == pilot.zone_id


# ----------------------- GET /apartments/{id}/serving-zones ---------------------


def test_apartment_serving_zones_endpoint(pg_db, pilot: PilotFixture) -> None:
    _map_zone_yard(pg_db, pilot.zone_id, _apartment_yard(pg_db, pilot.apartment_id))
    uid = seed_user(pg_db, roles="manager")
    resp = _client(uid, "manager").get(
        f"/api/v1/access/apartments/{pilot.apartment_id}/serving-zones"
    )
    assert resp.status_code == 200, resp.text
    assert any(z["id"] == pilot.zone_id for z in resp.json())


# ----------------------------- bot _resolve_zone_id -----------------------------


def test_resolve_zone_id_picks_first_when_multiple(pg_db, pilot: PilotFixture) -> None:
    """Несколько зон адреса → первая (минимальный id), без ZoneNotResolved."""
    yard = _apartment_yard(pg_db, pilot.apartment_id)
    _map_zone_yard(pg_db, pilot.zone_id, yard)
    z2 = _seed_zone(pg_db, "Зона 2")
    _map_zone_yard(pg_db, z2, yard)

    resolved = _resolve_zone_id(pg_db, pilot.apartment_id, None)
    assert resolved == min(pilot.zone_id, z2)


def test_resolve_zone_id_explicit_priority(pg_db, pilot: PilotFixture) -> None:
    assert _resolve_zone_id(pg_db, pilot.apartment_id, 777) == 777
