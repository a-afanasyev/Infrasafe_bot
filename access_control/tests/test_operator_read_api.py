"""READ-эндпоинты реестра access_control: история событий + база (§6, §11, §13.2).

Экраны охранника и менеджера (read-only). Покрываем:

* RBAC (§6.3, §6.2): без auth → 401; applicant/executor/inspector → 403;
  events/passes — security_operator/manager/system_admin; vehicles/requests —
  только manager/system_admin (security_operator → 403);
* фильтры, пагинацию (total/limit/offset), форму конверта ``{items,total,limit,offset}``;
* форму строк/детали (поля, которые нужны фронту).

PostgreSQL-only (как остальные тесты домена): сидинг через ``pg_db``/``pilot``,
коммит виден сессии запроса (синхронный get_db в контейнере).
"""
from __future__ import annotations

import datetime as dt
import json
import types
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.tests.conftest import (
    PilotFixture,
    seed_taxi_pass,
    seed_user,
    utcnow,
)
from uk_management_bot.api.dependencies import get_current_user


# --------------------------- auth/client хелперы ---------------------------


def _fake_user(uid: int, role: str, status: str = "approved"):
    return lambda: types.SimpleNamespace(
        id=uid, roles=json.dumps([role]), active_role=role, status=status
    )


def _client(uid: int, role: str, status: str = "approved") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, role, status)
    return TestClient(app)


# ------------------------------ сид-хелперы ------------------------------


def _seed_camera_event(
    db,
    pilot: PilotFixture,
    *,
    event_id: str,
    plate: str,
    captured_at: dt.datetime | None = None,
    source: str = "connected",
    direction: str = "entry",
    confidence: float | None = 0.9,
    attributes: dict | None = None,
    plate_photo_url: str | None = None,
    overview_photo_url: str | None = None,
) -> int:
    cap = captured_at or utcnow()
    return db.execute(
        text(
            "INSERT INTO camera_events "
            "(controller_id, event_id, gate_id, zone_id, direction, "
            " plate_number_original, plate_number_normalized, confidence, "
            " captured_at, received_at, source, attributes, "
            " plate_photo_url, overview_photo_url) "
            "VALUES (:c,:e,:g,:z,:d,:po,:pn,:conf,:cap, now(), :src, "
            " CAST(:attr AS JSONB), :pp, :op) RETURNING id"
        ),
        {
            "c": pilot.controller_id,
            "e": event_id,
            "g": pilot.gate_id,
            "z": pilot.zone_id,
            "d": direction,
            "po": plate,
            "pn": plate,
            "conf": confidence,
            "cap": cap,
            "src": source,
            "attr": json.dumps(attributes) if attributes is not None else None,
            "pp": plate_photo_url,
            "op": overview_photo_url,
        },
    ).scalar()


def _seed_decision(
    db,
    ce_id: int,
    *,
    decision: str,
    status: str,
    reason: str | None = None,
    group: str | None = None,
    supersedes: int | None = None,
    resolved_by: int | None = None,
) -> tuple[int, str]:
    grp = group or str(uuid.uuid4())
    did = db.execute(
        text(
            "INSERT INTO access_decisions "
            "(camera_event_id, decision_group_id, supersedes_decision_id, "
            " decision, status, reason, resolved_by_user_id, source) "
            "VALUES (:ce,:g,:sup,:dec,:st,:rs,:rb,'connected') RETURNING id"
        ),
        {
            "ce": ce_id,
            "g": grp,
            "sup": supersedes,
            "dec": decision,
            "st": status,
            "rs": reason,
            "rb": resolved_by,
        },
    ).scalar()
    return did, grp


def _seed_access_event(
    db,
    pilot: PilotFixture,
    ce_id: int,
    *,
    event_id: str,
    decision_id: int | None = None,
    occurred_at: dt.datetime | None = None,
) -> int:
    return db.execute(
        text(
            "INSERT INTO access_events "
            "(controller_id, event_id, camera_event_id, decision_id, gate_id, "
            " zone_id, direction, occurred_at, source) "
            "VALUES (:c,:e,:ce,:did,:g,:z,'entry',:occ,'connected') RETURNING id"
        ),
        {
            "c": pilot.controller_id,
            "e": event_id,
            "ce": ce_id,
            "did": decision_id,
            "g": pilot.gate_id,
            "z": pilot.zone_id,
            "occ": occurred_at or utcnow(),
        },
    ).scalar()


def _seed_command(db, pilot: PilotFixture, *, decision_id: int) -> str:
    cmd = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO barrier_commands "
            "(command_id, decision_id, controller_id, barrier_id, command_type, "
            " status, attempts, max_attempts) "
            "VALUES (:cmd,:did,:cid,:bid,'open_barrier','pending',0,5)"
        ),
        {
            "cmd": cmd,
            "did": decision_id,
            "cid": pilot.controller_id,
            "bid": pilot.barrier_id,
        },
    )
    db.commit()
    return cmd


def _seed_vehicle(
    db,
    pilot: PilotFixture,
    *,
    normalized: str,
    status: str = "active",
    with_link: bool = True,
    relation: str = "owner",
) -> int:
    vid = db.execute(
        text(
            "INSERT INTO vehicles "
            "(plate_number_original, plate_number_normalized, plate_country, "
            " make, model, color, vehicle_class, status) "
            "VALUES (:po,:pn,'UZ','Chevrolet','Cobalt','white','car',:st) RETURNING id"
        ),
        {"po": normalized, "pn": normalized, "st": status},
    ).scalar()
    if with_link:
        db.execute(
            text(
                "INSERT INTO vehicle_apartments "
                "(vehicle_id, apartment_id, relation_type, status) "
                "VALUES (:v,:a,:rt,'active')"
            ),
            {"v": vid, "a": pilot.apartment_id, "rt": relation},
        )
    db.commit()
    return vid


def _seed_request(
    db,
    pilot: PilotFixture,
    user_id: int,
    *,
    plate: str,
    status: str = "pending",
    relation: str = "owner",
) -> int:
    rid = db.execute(
        text(
            "INSERT INTO resident_access_requests "
            "(apartment_id, created_by_user_id, plate_number_original, "
            " plate_number_normalized, relation_type, status) "
            "VALUES (:a,:u,:po,:pn,:rt,:st) RETURNING id"
        ),
        {
            "a": pilot.apartment_id,
            "u": user_id,
            "po": plate,
            "pn": plate,
            "rt": relation,
            "st": status,
        },
    ).scalar()
    db.commit()
    return rid


# ============================ роутер зарегистрирован ============================


def test_registry_router_registered() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/api/v1/access/events" in paths
    assert "/api/v1/access/events/{event_id}" in paths
    assert "/api/v1/access/vehicles" in paths
    assert "/api/v1/access/vehicles/{vehicle_id}" in paths
    assert "/api/v1/access/passes" in paths
    assert "/api/v1/access/requests" in paths


# ================================ RBAC: 401 ================================

_READ_GET_PATHS = (
    "/api/v1/access/events",
    "/api/v1/access/vehicles",
    "/api/v1/access/passes",
    "/api/v1/access/requests",
)


def test_all_read_endpoints_require_auth_401(pg_db) -> None:
    client = TestClient(create_app())
    for path in _READ_GET_PATHS:
        resp = client.get(path)
        assert resp.status_code == 401, path


# =============================== RBAC: 403 ===============================


def test_applicant_forbidden_all_403(pg_db) -> None:
    uid = seed_user(pg_db, roles="applicant")
    client = _client(uid, "applicant")
    for path in _READ_GET_PATHS:
        assert client.get(path).status_code == 403, path


def test_executor_forbidden_all_403(pg_db) -> None:
    uid = seed_user(pg_db, roles="executor")
    client = _client(uid, "executor")
    for path in _READ_GET_PATHS:
        assert client.get(path).status_code == 403, path


def test_inspector_forbidden_all_403(pg_db) -> None:
    uid = seed_user(pg_db, roles="inspector")
    client = _client(uid, "inspector")
    for path in _READ_GET_PATHS:
        assert client.get(path).status_code == 403, path


def test_security_operator_forbidden_vehicles_and_requests_403(pg_db) -> None:
    """§6.3: оператор не управляет базой авто/заявок → 403 на vehicles/requests."""
    uid = seed_user(pg_db, roles="security_operator")
    client = _client(uid, "security_operator")
    assert client.get("/api/v1/access/vehicles").status_code == 403
    assert client.get("/api/v1/access/requests").status_code == 403


def test_security_operator_allowed_events_and_passes_200(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="security_operator")
    client = _client(uid, "security_operator")
    assert client.get("/api/v1/access/events").status_code == 200
    assert client.get("/api/v1/access/passes").status_code == 200


def test_manager_allowed_all_200(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    for path in _READ_GET_PATHS:
        assert client.get(path).status_code == 200, path


def test_system_admin_allowed_all_200(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="system_admin")
    client = _client(uid, "system_admin")
    for path in _READ_GET_PATHS:
        assert client.get(path).status_code == 200, path


def test_operator_not_approved_403(pg_db) -> None:
    """require_approved_roles: роль есть, но status != approved → 403."""
    uid = seed_user(pg_db, roles="security_operator", status="pending")
    client = _client(uid, "security_operator", status="pending")
    assert client.get("/api/v1/access/events").status_code == 403


# =============================== конверт ===============================


def test_envelope_shape(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    body = client.get("/api/v1/access/events").json()
    assert set(body.keys()) == {"items", "total", "limit", "offset"}
    assert isinstance(body["items"], list)
    assert body["limit"] == 50
    assert body["offset"] == 0


# =============================== /events ===============================


def test_events_row_shape_and_has_command(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="security_operator")
    ce = _seed_camera_event(pg_db, pilot, event_id="ev-1", plate="01A111AA")
    did, _ = _seed_decision(pg_db, ce, decision="allow", status="allowed")
    _seed_access_event(pg_db, pilot, ce, event_id="ev-1", decision_id=did)
    _seed_command(pg_db, pilot, decision_id=did)
    pg_db.commit()

    client = _client(uid, "security_operator")
    body = client.get("/api/v1/access/events").json()
    assert body["total"] == 1
    row = body["items"][0]
    for field in (
        "id",
        "event_id",
        "controller_id",
        "zone_id",
        "gate_id",
        "direction",
        "plate_number_normalized",
        "captured_at",
        "occurred_at",
        "source",
        "decision",
        "status",
        "reason",
        "decision_id",
        "resolved_by_user_id",
        "has_command",
        "plate_photo_url",
        "overview_photo_url",
    ):
        assert field in row, field
    assert row["event_id"] == "ev-1"
    assert row["decision"] == "allow"
    assert row["status"] == "allowed"
    assert row["decision_id"] == did
    assert row["has_command"] is True
    assert row["occurred_at"] is not None


def test_events_row_includes_photo_urls(pg_db, pilot) -> None:
    """§9.4/§11: список событий отдаёт фото-ссылки для экрана охраны."""
    uid = seed_user(pg_db, roles="security_operator")
    _seed_camera_event(
        pg_db,
        pilot,
        event_id="ev-photo",
        plate="01PH000",
        plate_photo_url="https://cdn.example/plate/ev-photo.jpg",
        overview_photo_url="https://cdn.example/overview/ev-photo.jpg",
    )
    pg_db.commit()
    client = _client(uid, "security_operator")
    body = client.get("/api/v1/access/events?plate=01PH000").json()
    assert body["total"] == 1
    row = body["items"][0]
    assert row["plate_photo_url"] == "https://cdn.example/plate/ev-photo.jpg"
    assert row["overview_photo_url"] == "https://cdn.example/overview/ev-photo.jpg"


def test_events_current_decision_is_latest_in_group(pg_db, pilot) -> None:
    """Текущее решение группы = последняя (не замещённая) строка."""
    uid = seed_user(pg_db, roles="manager")
    ce = _seed_camera_event(pg_db, pilot, event_id="ev-grp", plate="01G000GG")
    init, grp = _seed_decision(
        pg_db, ce, decision="manual_review", status="pending_review"
    )
    _seed_decision(
        pg_db,
        ce,
        decision="manual_review",
        status="allowed_manually",
        group=grp,
        supersedes=init,
    )
    pg_db.commit()
    client = _client(uid, "manager")
    body = client.get("/api/v1/access/events?plate=01G000GG").json()
    assert body["items"][0]["status"] == "allowed_manually"


def test_events_filter_by_decision(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="manager")
    a = _seed_camera_event(pg_db, pilot, event_id="ev-a", plate="01A000AA")
    _seed_decision(pg_db, a, decision="allow", status="allowed")
    d = _seed_camera_event(pg_db, pilot, event_id="ev-d", plate="01D000DD")
    _seed_decision(pg_db, d, decision="deny", status="denied")
    pg_db.commit()
    client = _client(uid, "manager")
    body = client.get("/api/v1/access/events?decision=deny").json()
    assert body["total"] == 1
    assert body["items"][0]["decision"] == "deny"


def test_events_filter_by_plate_contains(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="manager")
    _seed_camera_event(pg_db, pilot, event_id="ev-p1", plate="01XYZ77")
    _seed_camera_event(pg_db, pilot, event_id="ev-p2", plate="01ABC11")
    pg_db.commit()
    client = _client(uid, "manager")
    body = client.get("/api/v1/access/events?plate=xyz").json()
    assert body["total"] == 1
    assert body["items"][0]["plate_number_normalized"] == "01XYZ77"


def test_events_filter_by_source_and_zone(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="manager")
    _seed_camera_event(
        pg_db, pilot, event_id="ev-on", plate="01ON000", source="connected"
    )
    _seed_camera_event(
        pg_db, pilot, event_id="ev-off", plate="01OFF00", source="edge_offline"
    )
    pg_db.commit()
    client = _client(uid, "manager")
    body = client.get("/api/v1/access/events?source=edge_offline").json()
    assert body["total"] == 1
    assert body["items"][0]["source"] == "edge_offline"
    zbody = client.get(f"/api/v1/access/events?zone_id={pilot.zone_id}").json()
    assert zbody["total"] == 2


def test_events_pagination(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="manager")
    base = utcnow()
    for i in range(5):
        _seed_camera_event(
            pg_db,
            pilot,
            event_id=f"ev-pg-{i}",
            plate=f"01P00{i}P",
            captured_at=base - dt.timedelta(minutes=i),
        )
    pg_db.commit()
    client = _client(uid, "manager")
    body = client.get("/api/v1/access/events?limit=2&offset=0").json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert len(body["items"]) == 2
    body2 = client.get("/api/v1/access/events?limit=2&offset=4").json()
    assert len(body2["items"]) == 1


def test_events_sorted_desc_by_captured_at(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="manager")
    base = utcnow()
    _seed_camera_event(
        pg_db, pilot, event_id="ev-old", plate="01OLD00",
        captured_at=base - dt.timedelta(hours=1),
    )
    _seed_camera_event(pg_db, pilot, event_id="ev-new", plate="01NEW00", captured_at=base)
    pg_db.commit()
    client = _client(uid, "manager")
    items = client.get("/api/v1/access/events").json()["items"]
    assert items[0]["event_id"] == "ev-new"
    assert items[1]["event_id"] == "ev-old"


# =========================== /events/{event_id} ===========================


def test_event_detail_full_chain(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="security_operator")
    ce = _seed_camera_event(
        pg_db,
        pilot,
        event_id="ev-det",
        plate="01DET00",
        attributes={"vehicle_class": "car", "color": "red"},
    )
    init, grp = _seed_decision(
        pg_db, ce, decision="manual_review", status="pending_review"
    )
    did2, _ = _seed_decision(
        pg_db,
        ce,
        decision="manual_review",
        status="allowed_manually",
        group=grp,
        supersedes=init,
    )
    _seed_command(pg_db, pilot, decision_id=did2)
    pg_db.commit()
    client = _client(uid, "security_operator")
    resp = client.get(f"/api/v1/access/events/{ce}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["camera_event"]["id"] == ce
    assert body["camera_event"]["confidence"] is not None
    assert body["camera_event"]["vehicle_class"] == "car"
    assert body["camera_event"]["color"] == "red"
    assert len(body["decisions"]) == 2
    # цепочка по возрастанию id: вторая строка замещает первую
    assert body["decisions"][1]["supersedes_decision_id"] == init
    assert "row_hash" in body["decisions"][0]
    assert len(body["barrier_commands"]) == 1
    assert isinstance(body["manual_openings"], list)


def test_event_detail_404(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    assert client.get("/api/v1/access/events/999999").status_code == 404


# =============================== /vehicles ===============================


def test_vehicles_row_shape_and_relations(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="manager")
    vid = _seed_vehicle(pg_db, pilot, normalized="01V000VV")
    client = _client(uid, "manager")
    body = client.get("/api/v1/access/vehicles").json()
    assert body["total"] == 1
    row = body["items"][0]
    for field in (
        "id",
        "plate_number_original",
        "plate_number_normalized",
        "plate_country",
        "plate_type",
        "brand",
        "model",
        "color",
        "vehicle_class",
        "status",
        "blocked_reason",
        "blocked_by_user_id",
        "blocked_at",
        "apartments",
    ):
        assert field in row, field
    assert row["id"] == vid
    assert row["brand"] == "Chevrolet"
    assert len(row["apartments"]) == 1
    link = row["apartments"][0]
    assert link["apartment_id"] == pilot.apartment_id
    assert link["relation_type"] == "owner"
    assert link["status"] == "active"


def test_vehicles_filter_by_status(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="manager")
    _seed_vehicle(pg_db, pilot, normalized="01ACT00", status="active")
    _seed_vehicle(pg_db, pilot, normalized="01BLK00", status="blocked", with_link=False)
    client = _client(uid, "manager")
    body = client.get("/api/v1/access/vehicles?status=blocked").json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "blocked"


def test_vehicles_filter_by_plate_and_apartment(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="manager")
    _seed_vehicle(pg_db, pilot, normalized="01FIND0")
    _seed_vehicle(pg_db, pilot, normalized="01OTHER", with_link=False)
    client = _client(uid, "manager")
    body = client.get("/api/v1/access/vehicles?plate=find").json()
    assert body["total"] == 1
    abody = client.get(
        f"/api/v1/access/vehicles?apartment_id={pilot.apartment_id}"
    ).json()
    assert abody["total"] == 1
    assert abody["items"][0]["plate_number_normalized"] == "01FIND0"


def test_vehicle_detail_with_events(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="manager")
    vid = _seed_vehicle(pg_db, pilot, normalized="01DETV0")
    ce = _seed_camera_event(pg_db, pilot, event_id="ev-veh", plate="01DETV0")
    _seed_decision(pg_db, ce, decision="allow", status="allowed")
    pg_db.commit()
    client = _client(uid, "manager")
    resp = client.get(f"/api/v1/access/vehicles/{vid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["vehicle"]["id"] == vid
    assert len(body["apartments"]) == 1
    assert len(body["recent_events"]) == 1
    assert body["recent_events"][0]["event_id"] == "ev-veh"


def test_vehicle_detail_404(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="manager")
    client = _client(uid, "manager")
    assert client.get("/api/v1/access/vehicles/999999").status_code == 404


# =============================== /passes ===============================


def test_passes_row_shape_and_filters(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="security_operator")
    seed_taxi_pass(pg_db, pilot, normalized="01TAXI0", status="active")
    seed_taxi_pass(pg_db, pilot, normalized="01USED0", status="used")
    client = _client(uid, "security_operator")
    body = client.get("/api/v1/access/passes").json()
    assert body["total"] == 2
    row = body["items"][0]
    for field in (
        "id",
        "pass_type",
        "apartment_id",
        "created_by_user_id",
        "zone_id",
        "plate_number_original",
        "plate_number_normalized",
        "valid_from",
        "valid_until",
        "max_entries",
        "used_entries",
        "status",
        "source",
        "created_at",
    ):
        assert field in row, field
    used = client.get("/api/v1/access/passes?status=used").json()
    assert used["total"] == 1
    assert used["items"][0]["status"] == "used"
    taxi = client.get("/api/v1/access/passes?pass_type=taxi").json()
    assert taxi["total"] == 2


def test_passes_filter_by_apartment(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="manager")
    seed_taxi_pass(pg_db, pilot, normalized="01APT00")
    client = _client(uid, "manager")
    body = client.get(
        f"/api/v1/access/passes?apartment_id={pilot.apartment_id}"
    ).json()
    assert body["total"] == 1


# =============================== /requests ===============================


def test_requests_row_shape_and_filters(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="manager")
    _seed_request(pg_db, pilot, uid, plate="01REQ00", status="pending")
    _seed_request(pg_db, pilot, uid, plate="01APP00", status="approved")
    client = _client(uid, "manager")
    body = client.get("/api/v1/access/requests").json()
    assert body["total"] == 2
    row = body["items"][0]
    for field in (
        "id",
        "apartment_id",
        "created_by_user_id",
        "vehicle_id",
        "plate_number_original",
        "plate_number_normalized",
        "relation_type",
        "status",
        "reviewed_by_user_id",
        "reviewed_at",
        "review_comment",
        "created_at",
    ):
        assert field in row, field
    pend = client.get("/api/v1/access/requests?status=pending").json()
    assert pend["total"] == 1
    assert pend["items"][0]["status"] == "pending"


def test_requests_filter_by_apartment(pg_db, pilot) -> None:
    uid = seed_user(pg_db, roles="system_admin")
    _seed_request(pg_db, pilot, uid, plate="01RAPT0", status="pending")
    client = _client(uid, "system_admin")
    body = client.get(
        f"/api/v1/access/requests?apartment_id={pilot.apartment_id}"
    ).json()
    assert body["total"] == 1
