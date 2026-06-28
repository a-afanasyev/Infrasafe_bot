"""Тесты тумблера лимита мест (enforce_limit) + занятости (§10.3, §6.2, §6.4).

Покрывает:
* менеджерский тумблер: PATCH ``/admin/spot-assignments/{id}`` принимает
  ``enforce_limit`` (manager 200, applicant 403); значение отражается в
  ``AssignmentRow``;
* занятость в выдаче закреплений admin: ``occupied`` (открытые presence-сессии
  квартиры в зоне) и ``spots`` (активные закрепления квартиры в зоне) — «занято X из Y»;
* резидентский раздел «Моё место»: ``GET /my/spots`` (свои закрепления + занятость
  + enforce_limit; чужие не видны) и ``POST /my/spot-assignments/{id}/toggle-limit``
  (включить/выключить лимит на СВОЁМ закреплении; чужое → 403; идемпотентно);
* интеграция: житель снял лимит → 2-й авто пускают (assigned_spot_allowed, не
  parking_spot_occupied); вернул лимит → снова manual_review.

Все тесты требуют postgres (presence-сессии, partial-unique, ON CONFLICT).
"""
from __future__ import annotations

import datetime as dt
import json
import types
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from access_control.app.main import create_app
from access_control.services.ingestion import AnprIngestInput, ingest_anpr
from access_control.tests.conftest import (
    PilotFixture,
    seed_permanent_vehicle,
    seed_user,
    utcnow,
)
from uk_management_bot.api.dependencies import get_current_user


# ------------------------------ хелперы ------------------------------


def _payload(pilot, *, event_id, plate, direction="entry", captured_at=None):
    return AnprIngestInput(
        controller_id=pilot.controller_id,
        event_id=event_id,
        zone_id=pilot.zone_id,
        gate_id=pilot.gate_id,
        camera_id=pilot.camera_id,
        barrier_id=pilot.barrier_id,
        plate_number_original=plate,
        direction=direction,
        confidence=0.95,
        captured_at=captured_at or utcnow(),
    )


def _set_assigned(db: Session, zone_id: int) -> None:
    db.execute(
        text("UPDATE parking_zones SET parking_type = 'assigned' WHERE id = :z"),
        {"z": zone_id},
    )
    db.commit()


def _create_spot(db: Session, zone_id: int) -> int:
    return db.execute(
        text(
            "INSERT INTO parking_spots (zone_id, code, status) "
            "VALUES (:z, :c, 'active') RETURNING id"
        ),
        {"z": zone_id, "c": f"spot-{uuid.uuid4().hex[:6]}"},
    ).scalar_one()


def _assign_spot(
    db: Session, *, spot_id: int, apartment_id: int, enforce_limit: bool = True
) -> int:
    sid = db.execute(
        text(
            "INSERT INTO parking_spot_assignments "
            "(spot_id, apartment_id, ownership_type, status, enforce_limit) "
            "VALUES (:sp, :ap, 'owned', 'active', :en) RETURNING id"
        ),
        {"sp": spot_id, "ap": apartment_id, "en": enforce_limit},
    ).scalar_one()
    db.commit()
    return sid


def _seed_apartment(db: Session) -> int:
    """Создать отдельную (чужую) квартиру yard→building→apartment."""
    suffix = uuid.uuid4().hex[:8]
    yard_id = db.execute(
        text("INSERT INTO yards (name, is_active) VALUES (:n, true) RETURNING id"),
        {"n": f"ac-yard-{suffix}"},
    ).scalar_one()
    building_id = db.execute(
        text(
            "INSERT INTO buildings "
            "(address, yard_id, entrance_count, floor_count, is_active) "
            "VALUES (:a, :y, 1, 1, true) RETURNING id"
        ),
        {"a": f"ac-bld-{suffix}", "y": yard_id},
    ).scalar_one()
    apt = db.execute(
        text(
            "INSERT INTO apartments (building_id, apartment_number, is_active) "
            "VALUES (:b, :n, true) RETURNING id"
        ),
        {"b": building_id, "n": f"{suffix[:4]}"},
    ).scalar_one()
    db.commit()
    return apt


def _seed_resident(db: Session, apartment_id: int) -> int:
    """applicant-пользователь + approved-связь с квартирой. Вернуть user_id."""
    uid = seed_user(db, roles="applicant")
    db.execute(
        text(
            "INSERT INTO user_apartments "
            "(user_id, apartment_id, status, is_owner, is_primary) "
            "VALUES (:u, :a, 'approved', true, true)"
        ),
        {"u": uid, "a": apartment_id},
    )
    db.commit()
    return uid


def _fake_user(uid: int, role: str, status: str = "approved"):
    return lambda: types.SimpleNamespace(
        id=uid, roles=json.dumps([role]), active_role=role, status=status
    )


def _client_as(uid: int, role: str) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, role)
    return TestClient(app)


# =============================== менеджерский тумблер ===============================


def test_admin_patch_enforce_limit_manager_200(pg_db, pilot: PilotFixture) -> None:
    """manager PATCH enforce_limit=False → 200, значение в AssignmentRow."""
    spot = _create_spot(pg_db, pilot.zone_id)
    aid = _assign_spot(pg_db, spot_id=spot, apartment_id=pilot.apartment_id)
    uid = seed_user(pg_db, roles="manager")
    resp = _client_as(uid, "manager").patch(
        f"/api/v1/access/admin/spot-assignments/{aid}",
        json={"enforce_limit": False},
    )
    assert resp.status_code == 200
    assert resp.json()["enforce_limit"] is False


def test_admin_patch_enforce_limit_applicant_403(pg_db, pilot: PilotFixture) -> None:
    """applicant (не зоновая роль) PATCH enforce_limit → 403."""
    spot = _create_spot(pg_db, pilot.zone_id)
    aid = _assign_spot(pg_db, spot_id=spot, apartment_id=pilot.apartment_id)
    uid = seed_user(pg_db, roles="applicant")
    resp = _client_as(uid, "applicant").patch(
        f"/api/v1/access/admin/spot-assignments/{aid}",
        json={"enforce_limit": False},
    )
    assert resp.status_code == 403


def test_admin_list_assignment_occupancy(pg_db, pilot: PilotFixture) -> None:
    """В списке закреплений admin: enforce_limit + occupied/spots (1 сессия, 1 место)."""
    _set_assigned(pg_db, pilot.zone_id)
    seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA", with_rule=False)
    spot = _create_spot(pg_db, pilot.zone_id)
    _assign_spot(pg_db, spot_id=spot, apartment_id=pilot.apartment_id)
    ingest_anpr(pg_db, _payload(pilot, event_id="e1", plate="01A001AA"))

    uid = seed_user(pg_db, roles="manager")
    resp = _client_as(uid, "manager").get(
        f"/api/v1/access/admin/spot-assignments?apartment_id={pilot.apartment_id}"
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    row = items[0]
    assert row["enforce_limit"] is True
    assert row["occupied"] == 1
    assert row["spots"] == 1


# =============================== резидент: «Моё место» ===============================


def test_my_spots_lists_own_only(pg_db, pilot: PilotFixture) -> None:
    """Житель видит свои закрепления (+occupied/spots/enforce_limit); чужие — нет."""
    _set_assigned(pg_db, pilot.zone_id)
    seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA", with_rule=False)
    my_spot = _create_spot(pg_db, pilot.zone_id)
    _assign_spot(pg_db, spot_id=my_spot, apartment_id=pilot.apartment_id)
    ingest_anpr(pg_db, _payload(pilot, event_id="e1", plate="01A001AA"))

    # Чужая квартира с собственным закреплением в той же зоне.
    foreign_apt = _seed_apartment(pg_db)
    foreign_spot = _create_spot(pg_db, pilot.zone_id)
    _assign_spot(pg_db, spot_id=foreign_spot, apartment_id=foreign_apt)

    uid = _seed_resident(pg_db, pilot.apartment_id)
    resp = _client_as(uid, "applicant").get("/api/v1/access/my/spots")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    row = items[0]
    assert row["apartment_id"] == pilot.apartment_id
    assert row["spot_code"]
    assert row["zone_id"] == pilot.zone_id
    assert row["ownership_type"] == "owned"
    assert row["enforce_limit"] is True
    assert row["occupied"] == 1
    assert row["spots"] == 1


def test_my_toggle_limit_foreign_403(pg_db, pilot: PilotFixture) -> None:
    """Тумблер на ЧУЖОМ закреплении → 403."""
    foreign_apt = _seed_apartment(pg_db)
    foreign_spot = _create_spot(pg_db, pilot.zone_id)
    foreign_aid = _assign_spot(pg_db, spot_id=foreign_spot, apartment_id=foreign_apt)

    uid = _seed_resident(pg_db, pilot.apartment_id)
    resp = _client_as(uid, "applicant").post(
        f"/api/v1/access/my/spot-assignments/{foreign_aid}/toggle-limit",
        json={"enabled": False},
    )
    assert resp.status_code == 403


def test_my_toggle_limit_idempotent(pg_db, pilot: PilotFixture) -> None:
    """Повторный одинаковый тумблер → replayed True (идемпотентно)."""
    spot = _create_spot(pg_db, pilot.zone_id)
    aid = _assign_spot(pg_db, spot_id=spot, apartment_id=pilot.apartment_id)
    uid = _seed_resident(pg_db, pilot.apartment_id)
    client = _client_as(uid, "applicant")

    r1 = client.post(
        f"/api/v1/access/my/spot-assignments/{aid}/toggle-limit",
        json={"enabled": False},
    )
    assert r1.status_code == 200
    assert r1.json()["enforce_limit"] is False
    assert r1.json()["replayed"] is False

    r2 = client.post(
        f"/api/v1/access/my/spot-assignments/{aid}/toggle-limit",
        json={"enabled": False},
    )
    assert r2.status_code == 200
    assert r2.json()["replayed"] is True


def test_my_toggle_limit_integration(pg_db, pilot: PilotFixture) -> None:
    """Житель снял лимит → 2-й авто allow; вернул лимит → снова manual_review."""
    _set_assigned(pg_db, pilot.zone_id)
    seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA", with_rule=False)
    seed_permanent_vehicle(pg_db, pilot, normalized="01A002AA", with_rule=False)
    spot = _create_spot(pg_db, pilot.zone_id)
    aid = _assign_spot(pg_db, spot_id=spot, apartment_id=pilot.apartment_id)
    uid = _seed_resident(pg_db, pilot.apartment_id)
    client = _client_as(uid, "applicant")

    t0 = utcnow() - dt.timedelta(minutes=10)
    # 1-й авто занимает единственное место.
    ingest_anpr(pg_db, _payload(pilot, event_id="e1", plate="01A001AA", captured_at=t0))
    # 2-й авто при включённом лимите → manual_review parking_spot_occupied.
    blocked = ingest_anpr(
        pg_db, _payload(pilot, event_id="e2", plate="01A002AA", captured_at=t0)
    )
    assert blocked.decision == "manual_review"
    assert blocked.reason == "parking_spot_occupied"

    # Житель снимает лимит (2-я машина на 10 минут).
    off = client.post(
        f"/api/v1/access/my/spot-assignments/{aid}/toggle-limit",
        json={"enabled": False},
    )
    assert off.status_code == 200
    assert off.json()["enforce_limit"] is False

    # Теперь 2-й авто пускают (вне окна дедупа от e2).
    allowed = ingest_anpr(
        pg_db,
        _payload(
            pilot, event_id="e3", plate="01A002AA",
            captured_at=t0 + dt.timedelta(minutes=1),
        ),
    )
    assert allowed.decision == "allow"
    assert allowed.reason == "assigned_spot_allowed"

    # Житель возвращает лимит → снова manual_review.
    on = client.post(
        f"/api/v1/access/my/spot-assignments/{aid}/toggle-limit",
        json={"enabled": True},
    )
    assert on.status_code == 200
    assert on.json()["enforce_limit"] is True

    again = ingest_anpr(
        pg_db,
        _payload(
            pilot, event_id="e4", plate="01A002AA",
            captured_at=t0 + dt.timedelta(minutes=2),
        ),
    )
    assert again.decision == "manual_review"
    assert again.reason == "parking_spot_occupied"


def test_spot_limit_routes_registered() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/api/v1/access/my/spots" in paths
    assert (
        "/api/v1/access/my/spot-assignments/{assignment_id}/toggle-limit" in paths
    )
