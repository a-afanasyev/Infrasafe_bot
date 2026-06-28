"""Тесты выезда/presence-сессий + лимита мест assigned-зоны (§8.3, §10.3).

Решения владельца:
* assigned (подземная): не пускать авто квартиры сверх числа её активных мест —
  лишний при занятых местах → manual_review ``parking_spot_occupied`` (НЕ deny,
  команды нет); охрана решает.
* тумблер ``parking_spot_assignments.enforce_limit`` (default TRUE) — житель/
  менеджер может временно снять лимит (2-я машина) → enforce off → allow.
* выезд (``direction='exit'`` ИЛИ ручное закрытие) освобождает место.
* shared (надземная) — без лимита, поведение не меняется.
* выезд не расходует пропуск (§8.3); приём exit идемпотентен (§10.1).

Все тесты требуют postgres (advisory-lock, ON CONFLICT, partial-unique).
"""
from __future__ import annotations

import datetime as dt
import types
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

import access_control.services.ingestion as _ingestion  # noqa: F401
from access_control.app.main import create_app
from access_control.services.ingestion import AnprIngestInput, ingest_anpr
from access_control.tests.conftest import (
    PilotFixture,
    seed_permanent_vehicle,
    seed_taxi_pass,
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


def _set_shared(db: Session, zone_id: int) -> None:
    db.execute(
        text("UPDATE parking_zones SET parking_type = 'shared' WHERE id = :z"),
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
    db: Session,
    *,
    spot_id: int,
    apartment_id: int,
    enforce_limit: bool = True,
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


def _link_zone_to_apartment_yard(db: Session, zone_id: int, apartment_id: int) -> None:
    yard_id = db.execute(
        text(
            "SELECT b.yard_id FROM apartments a "
            "JOIN buildings b ON a.building_id = b.id WHERE a.id = :a"
        ),
        {"a": apartment_id},
    ).scalar_one()
    db.execute(
        text(
            "INSERT INTO parking_zone_yards (zone_id, yard_id) VALUES (:z, :y) "
            "ON CONFLICT (zone_id, yard_id) DO NOTHING"
        ),
        {"z": zone_id, "y": yard_id},
    )
    db.commit()


def _open_sessions(db: Session, apartment_id: int, zone_id: int) -> int:
    return db.execute(
        text(
            "SELECT count(*) FROM vehicle_presence_sessions "
            "WHERE apartment_id = :a AND zone_id = :z AND status = 'open'"
        ),
        {"a": apartment_id, "z": zone_id},
    ).scalar()


def _fake_user(uid: int, role: str, status: str = "approved"):
    import json

    return lambda: types.SimpleNamespace(
        id=uid, roles=json.dumps([role]), active_role=role, status=status
    )


# ------------------------- assigned: лимит мест -------------------------


def test_assigned_first_car_allowed_opens_session(pg_db, pilot: PilotFixture) -> None:
    """1 место/квартира, enforce on: 1-й авто allow + presence-сессия открыта."""
    _set_assigned(pg_db, pilot.zone_id)
    seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA", with_rule=False)
    spot = _create_spot(pg_db, pilot.zone_id)
    _assign_spot(pg_db, spot_id=spot, apartment_id=pilot.apartment_id)

    res = ingest_anpr(pg_db, _payload(pilot, event_id="e1", plate="01A001AA"))
    assert res.decision == "allow"
    assert res.reason == "assigned_spot_allowed"
    assert _open_sessions(pg_db, pilot.apartment_id, pilot.zone_id) == 1


def test_assigned_second_car_spot_occupied_manual_review(pg_db, pilot: PilotFixture) -> None:
    """Место занято 1-м авто → 2-й авто квартиры → manual_review, команды нет."""
    _set_assigned(pg_db, pilot.zone_id)
    seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA", with_rule=False)
    seed_permanent_vehicle(pg_db, pilot, normalized="01A002AA", with_rule=False)
    spot = _create_spot(pg_db, pilot.zone_id)
    _assign_spot(pg_db, spot_id=spot, apartment_id=pilot.apartment_id)

    ingest_anpr(pg_db, _payload(pilot, event_id="e1", plate="01A001AA"))
    res = ingest_anpr(pg_db, _payload(pilot, event_id="e2", plate="01A002AA"))
    assert res.decision == "manual_review"
    assert res.reason == "parking_spot_occupied"
    assert res.command is None


def test_exit_frees_spot_then_second_car_allowed(pg_db, pilot: PilotFixture) -> None:
    """Выезд 1-го авто (direction=exit) → место свободно → 2-й авто allow."""
    _set_assigned(pg_db, pilot.zone_id)
    seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA", with_rule=False)
    seed_permanent_vehicle(pg_db, pilot, normalized="01A002AA", with_rule=False)
    spot = _create_spot(pg_db, pilot.zone_id)
    _assign_spot(pg_db, spot_id=spot, apartment_id=pilot.apartment_id)

    # Разносим captured_at: повторный въезд 2-го авто (e3) не должен попасть в
    # 10-секундное окно дедупа с его первой попыткой (e2), иначе вернётся прежнее
    # решение, а не новое (§10.1).
    t0 = utcnow() - dt.timedelta(minutes=5)
    ingest_anpr(pg_db, _payload(pilot, event_id="e1", plate="01A001AA", captured_at=t0))
    # 2-й авто пока заблокирован (место занято).
    res_blocked = ingest_anpr(
        pg_db, _payload(pilot, event_id="e2", plate="01A002AA", captured_at=t0)
    )
    assert res_blocked.decision == "manual_review"

    # Выезд 1-го авто → сессия закрыта.
    res_exit = ingest_anpr(
        pg_db,
        _payload(
            pilot, event_id="x1", plate="01A001AA", direction="exit",
            captured_at=t0 + dt.timedelta(minutes=1),
        ),
    )
    assert res_exit.decision == "allow"
    assert _open_sessions(pg_db, pilot.apartment_id, pilot.zone_id) == 0

    # Теперь 2-й авто пускают (через окно дедупа от e2).
    res_ok = ingest_anpr(
        pg_db,
        _payload(
            pilot, event_id="e3", plate="01A002AA",
            captured_at=t0 + dt.timedelta(minutes=2),
        ),
    )
    assert res_ok.decision == "allow"
    assert res_ok.reason == "assigned_spot_allowed"


def test_enforce_limit_off_allows_second_car(pg_db, pilot: PilotFixture) -> None:
    """enforce_limit=FALSE на закреплении → 2-й авто пускают несмотря на занятость."""
    _set_assigned(pg_db, pilot.zone_id)
    seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA", with_rule=False)
    seed_permanent_vehicle(pg_db, pilot, normalized="01A002AA", with_rule=False)
    spot = _create_spot(pg_db, pilot.zone_id)
    _assign_spot(pg_db, spot_id=spot, apartment_id=pilot.apartment_id, enforce_limit=False)

    ingest_anpr(pg_db, _payload(pilot, event_id="e1", plate="01A001AA"))
    res = ingest_anpr(pg_db, _payload(pilot, event_id="e2", plate="01A002AA"))
    assert res.decision == "allow"
    assert res.reason == "assigned_spot_allowed"


def test_two_spots_allow_two_deny_third(pg_db, pilot: PilotFixture) -> None:
    """2 места/квартира: пускают 2 авто, 3-й → manual_review parking_spot_occupied."""
    _set_assigned(pg_db, pilot.zone_id)
    for plate in ("01A001AA", "01A002AA", "01A003AA"):
        seed_permanent_vehicle(pg_db, pilot, normalized=plate, with_rule=False)
    for _ in range(2):
        _assign_spot(
            pg_db, spot_id=_create_spot(pg_db, pilot.zone_id),
            apartment_id=pilot.apartment_id,
        )

    r1 = ingest_anpr(pg_db, _payload(pilot, event_id="e1", plate="01A001AA"))
    r2 = ingest_anpr(pg_db, _payload(pilot, event_id="e2", plate="01A002AA"))
    r3 = ingest_anpr(pg_db, _payload(pilot, event_id="e3", plate="01A003AA"))
    assert r1.decision == "allow"
    assert r2.decision == "allow"
    assert r3.decision == "manual_review"
    assert r3.reason == "parking_spot_occupied"


# ------------------------------ shared: без лимита ------------------------------


def test_shared_no_spot_limit(pg_db, pilot: PilotFixture) -> None:
    """shared-зона: лимит мест НЕ применяется — несколько авто квартиры → все allow."""
    _set_shared(pg_db, pilot.zone_id)
    _link_zone_to_apartment_yard(pg_db, pilot.zone_id, pilot.apartment_id)
    seed_permanent_vehicle(pg_db, pilot, normalized="01S001SS", with_rule=False)
    seed_permanent_vehicle(pg_db, pilot, normalized="01S002SS", with_rule=False)

    r1 = ingest_anpr(pg_db, _payload(pilot, event_id="e1", plate="01S001SS"))
    r2 = ingest_anpr(pg_db, _payload(pilot, event_id="e2", plate="01S002SS"))
    assert r1.decision == "allow"
    assert r1.reason == "shared_access_allowed"
    assert r2.decision == "allow"
    assert r2.reason == "shared_access_allowed"


# ------------------------- выезд: не расходует пропуск -------------------------


def test_exit_does_not_consume_pass_and_idempotent(pg_db, pilot: PilotFixture) -> None:
    """Выезд не расходует max_entries (§8.3); повтор exit event_id идемпотентен (§10.1)."""
    pid = seed_taxi_pass(pg_db, pilot, normalized="01T100TT", max_entries=1)
    entry = ingest_anpr(pg_db, _payload(pilot, event_id="in1", plate="01T100TT"))
    assert entry.decision == "allow"
    used_after_entry = pg_db.execute(
        text("SELECT used_entries FROM access_passes WHERE id = :p"), {"p": pid}
    ).scalar()
    assert used_after_entry == 1

    ex1 = ingest_anpr(
        pg_db, _payload(pilot, event_id="out1", plate="01T100TT", direction="exit")
    )
    assert ex1.decision == "allow"
    assert ex1.replayed is False
    # Повтор того же exit event_id → прежний результат, без новых записей.
    ex2 = ingest_anpr(
        pg_db, _payload(pilot, event_id="out1", plate="01T100TT", direction="exit")
    )
    assert ex2.replayed is True
    used_after_exit = pg_db.execute(
        text("SELECT used_entries FROM access_passes WHERE id = :p"), {"p": pid}
    ).scalar()
    assert used_after_exit == 1  # выезд НЕ израсходовал пропуск


# ------------------------- ручное освобождение места -------------------------


def _open_session_id(db: Session, apartment_id: int, zone_id: int) -> int:
    return db.execute(
        text(
            "SELECT id FROM vehicle_presence_sessions "
            "WHERE apartment_id = :a AND zone_id = :z AND status = 'open' "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"a": apartment_id, "z": zone_id},
    ).scalar()


def _seed_open_session(db: Session, pilot: PilotFixture) -> int:
    """Открыть presence-сессию через приём въезда; вернуть её id."""
    _set_assigned(db, pilot.zone_id)
    seed_permanent_vehicle(db, pilot, normalized="01A009AA", with_rule=False)
    _assign_spot(
        db, spot_id=_create_spot(db, pilot.zone_id), apartment_id=pilot.apartment_id
    )
    ingest_anpr(db, _payload(pilot, event_id="e9", plate="01A009AA"))
    return _open_session_id(db, pilot.apartment_id, pilot.zone_id)


def test_presence_close_requires_auth_401(pg_db, pilot: PilotFixture) -> None:
    sid = _seed_open_session(pg_db, pilot)
    client = TestClient(create_app())
    resp = client.post(f"/api/v1/access/presence/{sid}/close", json={"reason": "уехал"})
    assert resp.status_code == 401


def test_presence_close_forbidden_role_403(pg_db, pilot: PilotFixture) -> None:
    sid = _seed_open_session(pg_db, pilot)
    uid = seed_user(pg_db, roles="applicant")
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "applicant")
    resp = TestClient(app).post(
        f"/api/v1/access/presence/{sid}/close", json={"reason": "уехал"}
    )
    assert resp.status_code == 403


def test_presence_close_success_and_idempotent(pg_db, pilot: PilotFixture) -> None:
    sid = _seed_open_session(pg_db, pilot)
    uid = seed_user(pg_db, roles="security_operator")
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "security_operator")
    client = TestClient(app)

    resp = client.post(
        f"/api/v1/access/presence/{sid}/close", json={"reason": "машина уехала"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "closed"
    assert body["replayed"] is False
    assert _open_sessions(pg_db, pilot.apartment_id, pilot.zone_id) == 0

    # Идемпотентность: повтор закрытия → сохранённый результат, без падения.
    resp2 = client.post(
        f"/api/v1/access/presence/{sid}/close", json={"reason": "машина уехала"}
    )
    assert resp2.status_code == 200
    assert resp2.json()["replayed"] is True


def test_presence_close_not_found_404(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="manager")
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "manager")
    resp = TestClient(app).post(
        "/api/v1/access/presence/999999/close", json={"reason": "нет такой"}
    )
    assert resp.status_code == 404


def test_presence_router_registered() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/api/v1/access/presence/{session_id}/close" in paths


# ------------------- admin: список открытых presence-сессий -------------------


def test_admin_presence_route_registered() -> None:
    paths = {route.path for route in create_app().routes}
    assert "/api/v1/access/admin/presence" in paths


def test_admin_presence_requires_auth_401(pg_db, pilot: PilotFixture) -> None:
    _seed_open_session(pg_db, pilot)
    resp = TestClient(create_app()).get("/api/v1/access/admin/presence")
    assert resp.status_code == 401


def test_admin_presence_applicant_403(pg_db, pilot: PilotFixture) -> None:
    uid = seed_user(pg_db, roles="applicant")
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "applicant")
    resp = TestClient(app).get("/api/v1/access/admin/presence")
    assert resp.status_code == 403


def test_admin_presence_manager_lists_open_session(pg_db, pilot: PilotFixture) -> None:
    sid = _seed_open_session(pg_db, pilot)
    uid = seed_user(pg_db, roles="manager")
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "manager")
    resp = TestClient(app).get("/api/v1/access/admin/presence")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) >= {"items", "total", "limit", "offset"}
    assert body["total"] >= 1
    row = next(it for it in body["items"] if it["id"] == sid)
    assert row["zone_id"] == pilot.zone_id
    assert row["apartment_id"] == pilot.apartment_id
    assert row["plate_normalized"] == "01A009AA"
    assert row["entered_at"] is not None


def test_admin_presence_security_operator_ok(pg_db, pilot: PilotFixture) -> None:
    _seed_open_session(pg_db, pilot)
    uid = seed_user(pg_db, roles="security_operator")
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "security_operator")
    resp = TestClient(app).get("/api/v1/access/admin/presence")
    assert resp.status_code == 200


def test_admin_presence_filter_by_zone_and_apartment(pg_db, pilot: PilotFixture) -> None:
    sid = _seed_open_session(pg_db, pilot)
    uid = seed_user(pg_db, roles="manager")
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "manager")
    client = TestClient(app)

    by_zone = client.get(f"/api/v1/access/admin/presence?zone_id={pilot.zone_id}").json()
    assert any(it["id"] == sid for it in by_zone["items"])
    by_apt = client.get(
        f"/api/v1/access/admin/presence?apartment_id={pilot.apartment_id}"
    ).json()
    assert any(it["id"] == sid for it in by_apt["items"])

    # Несуществующая зона → пусто.
    empty = client.get("/api/v1/access/admin/presence?zone_id=999999").json()
    assert empty["total"] == 0
    assert empty["items"] == []


def test_admin_presence_excludes_closed_session(pg_db, pilot: PilotFixture) -> None:
    sid = _seed_open_session(pg_db, pilot)
    operator = seed_user(pg_db, roles="manager")
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(operator, "manager")
    client = TestClient(app)

    before = client.get("/api/v1/access/admin/presence").json()
    assert any(it["id"] == sid for it in before["items"])

    closed = client.post(
        f"/api/v1/access/presence/{sid}/close", json={"reason": "освободить место"}
    )
    assert closed.status_code == 200, closed.text

    after = client.get("/api/v1/access/admin/presence").json()
    assert all(it["id"] != sid for it in after["items"])
