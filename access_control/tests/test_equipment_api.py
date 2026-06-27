"""Ф?: ADMIN-эндпоинты управления оборудованием контроля доступа (§6.1, §6.2, §9.1).

Покрывает реестр оборудования точки въезда (zone→gate→camera→barrier→controller)
поверх общей базы access_control (USER-API, JWT/cookie — ``require_approved_roles``,
НЕ device-auth):

* зоны (parking_zones) + привязка фаз (parking_zone_yards) и въезды (access_gates)
  — manager/system_admin (§6.2 «настройка зон»);
* камеры/шлагбаумы/edge-контроллеры + device-credentials — ТОЛЬКО system_admin (§6.1).

RBAC: нужная роль 200/201; лишняя роль 403; без auth 401; applicant/executor/
inspector/security_operator → 403 на admin-ресурсы (security_operator не «меняет
оборудование», §6.3).

Ключевое (§9.1, решение CTO #8): POST контроллера ГЕНЕРИРУЕТ device API-ключ,
возвращает PLAINTEXT ровно один раз, в БД кладёт ТОЛЬКО ``api_key_hash``; HMAC-секрет
не хранится (резолвится из seed+controller_uid). Созданный контроллер реально
проходит device-auth. rotate-key инвалидирует старый ключ. PostgreSQL-only.
"""
from __future__ import annotations

import types
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.services.device_auth import (
    hash_api_key,
    resolve_device_secret,
    sign_request,
)
from access_control.tests.conftest import seed_user
from uk_management_bot.api.dependencies import get_current_user


# ------------------------------ helpers ------------------------------


def _fake_user(uid: int, role: str, status: str = "approved"):
    import json

    return lambda: types.SimpleNamespace(
        id=uid, roles=json.dumps([role]), active_role=role, status=status
    )


def _client(uid: int, role: str, status: str = "approved") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, role, status)
    return TestClient(app)


def _seed_yard(db) -> int:
    yid = db.execute(
        text("INSERT INTO yards (name, is_active) VALUES (:n, true) RETURNING id"),
        {"n": f"ac-adm-yard-{uuid.uuid4().hex[:8]}"},
    ).scalar()
    db.commit()
    return yid


def _u(db, role: str) -> int:
    return seed_user(db, roles=role)


def _edge_get(controller_uid: str, api_key: str) -> int:
    """Подписать GET commands/next ключом устройства → код ответа (204=auth прошла)."""
    path = f"/api/v1/access/edge/{controller_uid}/commands/next"
    headers = sign_request(
        "GET",
        path,
        b"",
        controller_uid=controller_uid,
        api_key=api_key,
        secret=resolve_device_secret(controller_uid),
    )
    return TestClient(create_app()).get(path, headers=headers).status_code


def _new_uid() -> str:
    return f"adm-ctrl-{uuid.uuid4().hex[:8]}"


def _create_zone(client: TestClient, *, code: str | None = None) -> dict:
    resp = client.post(
        "/api/v1/access/admin/zones",
        json={"code": code or f"z-{uuid.uuid4().hex[:6]}", "name": "Зона"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_gate(client: TestClient, zone_id: int, *, code: str | None = None) -> dict:
    resp = client.post(
        "/api/v1/access/admin/gates",
        json={"code": code or f"g-{uuid.uuid4().hex[:6]}", "zone_id": zone_id,
              "direction": "entry", "name": "Въезд"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ------------------------------ router wiring ------------------------------


def test_admin_router_registered() -> None:
    paths = {route.path for route in create_app().routes}
    for p in (
        "/api/v1/access/admin/zones",
        "/api/v1/access/admin/zones/{zone_id}",
        "/api/v1/access/admin/zones/{zone_id}/yards",
        "/api/v1/access/admin/gates",
        "/api/v1/access/admin/gates/{gate_id}",
        "/api/v1/access/admin/cameras",
        "/api/v1/access/admin/cameras/{camera_id}",
        "/api/v1/access/admin/barriers",
        "/api/v1/access/admin/barriers/{barrier_id}",
        "/api/v1/access/admin/controllers",
        "/api/v1/access/admin/controllers/{controller_id}",
        "/api/v1/access/admin/controllers/{controller_id}/rotate-key",
    ):
        assert p in paths, f"маршрут не зарегистрирован: {p}"


# ------------------------------ RBAC: zones ------------------------------


def test_zones_requires_auth_401(pg_db) -> None:
    assert TestClient(create_app()).get("/api/v1/access/admin/zones").status_code == 401


def test_zones_manager_ok(pg_db) -> None:
    uid = _u(pg_db, "manager")
    assert _client(uid, "manager").get("/api/v1/access/admin/zones").status_code == 200


def test_zones_system_admin_ok(pg_db) -> None:
    uid = _u(pg_db, "system_admin")
    assert (
        _client(uid, "system_admin").get("/api/v1/access/admin/zones").status_code == 200
    )


def test_zones_security_operator_403(pg_db) -> None:
    uid = _u(pg_db, "security_operator")
    assert (
        _client(uid, "security_operator").get("/api/v1/access/admin/zones").status_code
        == 403
    )


def test_zones_applicant_403(pg_db) -> None:
    uid = _u(pg_db, "applicant")
    assert _client(uid, "applicant").get("/api/v1/access/admin/zones").status_code == 403


# ------------------------------ RBAC: gates ------------------------------


def test_gates_manager_ok(pg_db) -> None:
    uid = _u(pg_db, "manager")
    assert _client(uid, "manager").get("/api/v1/access/admin/gates").status_code == 200


def test_gates_security_operator_403(pg_db) -> None:
    uid = _u(pg_db, "security_operator")
    assert (
        _client(uid, "security_operator").get("/api/v1/access/admin/gates").status_code
        == 403
    )


# --------------------- RBAC: cameras/barriers/controllers (admin-only) ------


def test_cameras_manager_forbidden_403(pg_db) -> None:
    """§6.1: оборудование (камеры) — только system_admin; manager → 403."""
    uid = _u(pg_db, "manager")
    assert _client(uid, "manager").get("/api/v1/access/admin/cameras").status_code == 403


def test_cameras_system_admin_ok(pg_db) -> None:
    uid = _u(pg_db, "system_admin")
    assert (
        _client(uid, "system_admin").get("/api/v1/access/admin/cameras").status_code == 200
    )


def test_barriers_manager_forbidden_403(pg_db) -> None:
    uid = _u(pg_db, "manager")
    assert _client(uid, "manager").get("/api/v1/access/admin/barriers").status_code == 403


def test_controllers_manager_forbidden_403(pg_db) -> None:
    uid = _u(pg_db, "manager")
    assert (
        _client(uid, "manager").get("/api/v1/access/admin/controllers").status_code == 403
    )


def test_controllers_requires_auth_401(pg_db) -> None:
    assert (
        TestClient(create_app()).get("/api/v1/access/admin/controllers").status_code == 401
    )


def test_controllers_security_operator_403(pg_db) -> None:
    uid = _u(pg_db, "security_operator")
    assert (
        _client(uid, "security_operator")
        .get("/api/v1/access/admin/controllers")
        .status_code
        == 403
    )


# ------------------------------ full chain create ------------------------------


def test_full_chain_zone_gate_camera_barrier_controller(pg_db) -> None:
    """§6.1: system_admin заводит полную цепочку реальной точки въезда."""
    uid = _u(pg_db, "system_admin")
    c = _client(uid, "system_admin")

    zone = _create_zone(c)
    gate = _create_gate(c, zone["id"])

    cam = c.post(
        "/api/v1/access/admin/cameras",
        json={"code": f"cam-{uuid.uuid4().hex[:6]}", "gate_id": gate["id"],
              "direction": "entry", "vendor": "Hikvision", "model": "DS-2CD",
              "attributes": {"fps": 25}},
    )
    assert cam.status_code == 201, cam.text
    assert cam.json()["vendor"] == "Hikvision"
    assert cam.json()["attributes"] == {"fps": 25}

    bar = c.post(
        "/api/v1/access/admin/barriers",
        json={"code": f"bar-{uuid.uuid4().hex[:6]}", "gate_id": gate["id"],
              "relay_type": "no", "config": {"pulse_ms": 500}},
    )
    assert bar.status_code == 201, bar.text
    assert bar.json()["relay_type"] == "no"

    uid_str = _new_uid()
    ctrl = c.post(
        "/api/v1/access/admin/controllers",
        json={"controller_uid": uid_str, "zone_id": zone["id"], "gate_id": gate["id"],
              "name": "Контроллер 1"},
    )
    assert ctrl.status_code == 201, ctrl.text
    body = ctrl.json()
    assert body["controller_uid"] == uid_str
    assert body["zone_id"] == zone["id"]
    assert body["gate_id"] == gate["id"]
    assert body["status"] == "active"
    assert body["is_active"] is True


# ------------------------------ envelope ------------------------------


def test_zones_list_envelope(pg_db) -> None:
    uid = _u(pg_db, "manager")
    c = _client(uid, "manager")
    _create_zone(c)
    page = c.get("/api/v1/access/admin/zones?limit=10&offset=0").json()
    assert set(page.keys()) >= {"items", "total", "limit", "offset"}
    assert page["limit"] == 10 and page["offset"] == 0
    assert page["total"] >= 1
    assert isinstance(page["items"], list)


# ------------------------------ device api_key lifecycle ------------------------------


def test_controller_create_returns_plaintext_key_once_and_hash_in_db(pg_db) -> None:
    """POST контроллера: plaintext api_key один раз; в БД только hash; в GET ключа нет."""
    uid = _u(pg_db, "system_admin")
    c = _client(uid, "system_admin")
    uid_str = _new_uid()
    created = c.post(
        "/api/v1/access/admin/controllers", json={"controller_uid": uid_str}
    )
    assert created.status_code == 201, created.text
    body = created.json()
    api_key = body["api_key"]
    assert isinstance(api_key, str) and len(api_key) >= 20
    cid = body["id"]

    # В БД — только хэш, совпадающий с hash_api_key(возвращённого ключа).
    stored = pg_db.execute(
        text("SELECT api_key_hash FROM edge_controllers WHERE id = :i"), {"i": cid}
    ).scalar()
    assert stored == hash_api_key(api_key)

    # GET не отдаёт ни api_key, ни api_key_hash (только безопасные поля).
    got = c.get(f"/api/v1/access/admin/controllers/{cid}")
    assert got.status_code == 200, got.text
    item = got.json()
    assert "api_key" not in item
    assert "api_key_hash" not in item

    # В списке тоже нет секрета.
    page = c.get("/api/v1/access/admin/controllers").json()
    for it in page["items"]:
        assert "api_key" not in it and "api_key_hash" not in it


def test_created_controller_passes_device_auth(pg_db) -> None:
    """§9.1: контроллер, созданный admin-API, реально проходит device-auth ключом."""
    uid = _u(pg_db, "system_admin")
    c = _client(uid, "system_admin")
    uid_str = _new_uid()
    body = c.post(
        "/api/v1/access/admin/controllers", json={"controller_uid": uid_str}
    ).json()
    api_key = body["api_key"]
    # Пустая очередь команд → 204 (значит device-auth прошла); неверный ключ → 401.
    assert _edge_get(uid_str, api_key) == 204
    assert _edge_get(uid_str, "wrong-key") == 401


def test_rotate_key_invalidates_old_key(pg_db) -> None:
    """rotate-key: новый plaintext один раз; старый ключ больше не аутентифицируется."""
    uid = _u(pg_db, "system_admin")
    c = _client(uid, "system_admin")
    uid_str = _new_uid()
    created = c.post(
        "/api/v1/access/admin/controllers", json={"controller_uid": uid_str}
    ).json()
    cid = created["id"]
    old_key = created["api_key"]
    assert _edge_get(uid_str, old_key) == 204

    rot = c.post(f"/api/v1/access/admin/controllers/{cid}/rotate-key")
    assert rot.status_code == 200, rot.text
    new_key = rot.json()["api_key"]
    assert new_key != old_key

    # Старый ключ инвалидирован, новый — работает.
    assert _edge_get(uid_str, old_key) == 401
    assert _edge_get(uid_str, new_key) == 204
    # В БД хэш совпадает с новым ключом.
    stored = pg_db.execute(
        text("SELECT api_key_hash FROM edge_controllers WHERE id = :i"), {"i": cid}
    ).scalar()
    assert stored == hash_api_key(new_key)


def test_rotate_key_unknown_controller_404(pg_db) -> None:
    uid = _u(pg_db, "system_admin")
    resp = _client(uid, "system_admin").post(
        "/api/v1/access/admin/controllers/999999/rotate-key"
    )
    assert resp.status_code == 404


# ------------------------------ uniqueness 409 ------------------------------


def test_zone_duplicate_code_409(pg_db) -> None:
    uid = _u(pg_db, "manager")
    c = _client(uid, "manager")
    code = f"dupz-{uuid.uuid4().hex[:6]}"
    assert c.post("/api/v1/access/admin/zones", json={"code": code, "name": "A"}).status_code == 201
    dup = c.post("/api/v1/access/admin/zones", json={"code": code, "name": "B"})
    assert dup.status_code == 409


def test_gate_duplicate_code_409(pg_db) -> None:
    uid = _u(pg_db, "manager")
    c = _client(uid, "manager")
    zone = _create_zone(c)
    code = f"dupg-{uuid.uuid4().hex[:6]}"
    _create_gate(c, zone["id"], code=code)
    dup = c.post(
        "/api/v1/access/admin/gates",
        json={"code": code, "zone_id": zone["id"], "direction": "entry"},
    )
    assert dup.status_code == 409


def test_controller_duplicate_uid_409(pg_db) -> None:
    uid = _u(pg_db, "system_admin")
    c = _client(uid, "system_admin")
    uid_str = _new_uid()
    assert c.post(
        "/api/v1/access/admin/controllers", json={"controller_uid": uid_str}
    ).status_code == 201
    dup = c.post(
        "/api/v1/access/admin/controllers", json={"controller_uid": uid_str}
    )
    assert dup.status_code == 409


# ------------------------------ FK / enum validation ------------------------------


def test_gate_bad_zone_id_422(pg_db) -> None:
    uid = _u(pg_db, "manager")
    resp = _client(uid, "manager").post(
        "/api/v1/access/admin/gates",
        json={"code": f"g-{uuid.uuid4().hex[:6]}", "zone_id": 999999, "direction": "entry"},
    )
    assert resp.status_code == 422


def test_camera_bad_gate_id_422(pg_db) -> None:
    uid = _u(pg_db, "system_admin")
    resp = _client(uid, "system_admin").post(
        "/api/v1/access/admin/cameras",
        json={"code": f"c-{uuid.uuid4().hex[:6]}", "gate_id": 999999, "direction": "entry"},
    )
    assert resp.status_code == 422


def test_zone_bad_offline_mode_422(pg_db) -> None:
    uid = _u(pg_db, "manager")
    resp = _client(uid, "manager").post(
        "/api/v1/access/admin/zones",
        json={"code": f"z-{uuid.uuid4().hex[:6]}", "name": "X", "offline_mode": "nonsense"},
    )
    assert resp.status_code == 422


def test_gate_bad_direction_422(pg_db) -> None:
    uid = _u(pg_db, "manager")
    c = _client(uid, "manager")
    zone = _create_zone(c)
    resp = c.post(
        "/api/v1/access/admin/gates",
        json={"code": f"g-{uuid.uuid4().hex[:6]}", "zone_id": zone["id"], "direction": "sideways"},
    )
    assert resp.status_code == 422


def test_patch_unknown_zone_404(pg_db) -> None:
    uid = _u(pg_db, "manager")
    resp = _client(uid, "manager").patch(
        "/api/v1/access/admin/zones/999999", json={"name": "renamed"}
    )
    assert resp.status_code == 404


# ------------------------------ PATCH happy paths ------------------------------


def test_patch_zone_updates_fields(pg_db) -> None:
    uid = _u(pg_db, "manager")
    c = _client(uid, "manager")
    zone = _create_zone(c)
    resp = c.patch(
        f"/api/v1/access/admin/zones/{zone['id']}",
        json={"name": "Новое имя", "max_permanent_per_apartment": 3, "is_active": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Новое имя"
    assert body["max_permanent_vehicles_per_apartment"] == 3
    assert body["is_active"] is False


def test_patch_controller_status_and_offline(pg_db) -> None:
    uid = _u(pg_db, "system_admin")
    c = _client(uid, "system_admin")
    cid = c.post(
        "/api/v1/access/admin/controllers", json={"controller_uid": _new_uid()}
    ).json()["id"]
    resp = c.patch(
        f"/api/v1/access/admin/controllers/{cid}",
        json={"status": "inactive", "ip_allowlist": ["10.0.0.0/24"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "inactive"
    assert resp.json()["ip_allowlist"] == ["10.0.0.0/24"]


# ------------------------------ zone yards ------------------------------


def test_zone_attach_and_detach_yards(pg_db) -> None:
    uid = _u(pg_db, "manager")
    c = _client(uid, "manager")
    zone = _create_zone(c)
    y1 = _seed_yard(pg_db)
    y2 = _seed_yard(pg_db)

    add = c.post(
        f"/api/v1/access/admin/zones/{zone['id']}/yards", json={"add": [y1, y2]}
    )
    assert add.status_code == 200, add.text
    assert sorted(add.json()["yard_ids"]) == sorted([y1, y2])

    # Идемпотентно: повторный add тех же — без дублей.
    again = c.post(
        f"/api/v1/access/admin/zones/{zone['id']}/yards", json={"add": [y1]}
    )
    assert sorted(again.json()["yard_ids"]) == sorted([y1, y2])

    rem = c.post(
        f"/api/v1/access/admin/zones/{zone['id']}/yards", json={"remove": [y1]}
    )
    assert rem.json()["yard_ids"] == [y2]


def test_zone_attach_unknown_yard_422(pg_db) -> None:
    uid = _u(pg_db, "manager")
    c = _client(uid, "manager")
    zone = _create_zone(c)
    resp = c.post(
        f"/api/v1/access/admin/zones/{zone['id']}/yards", json={"add": [999999]}
    )
    assert resp.status_code == 422


# ------------------------------ audit ------------------------------


def test_zone_create_writes_audit(pg_db) -> None:
    uid = _u(pg_db, "manager")
    c = _client(uid, "manager")
    body = _create_zone(c)
    row = pg_db.execute(
        text(
            "SELECT actor_user_id, action, entity_id, row_hash FROM access_audit_logs "
            "WHERE action = 'access.zone_create' AND entity_id = :e"
        ),
        {"e": str(body["id"])},
    ).first()
    assert row is not None
    assert row[0] == uid
    assert row[3] is not None  # hash-chain заполнен


def test_controller_create_and_rotate_write_audit(pg_db) -> None:
    uid = _u(pg_db, "system_admin")
    c = _client(uid, "system_admin")
    created = c.post(
        "/api/v1/access/admin/controllers", json={"controller_uid": _new_uid()}
    ).json()
    cid = created["id"]
    c.post(f"/api/v1/access/admin/controllers/{cid}/rotate-key")
    actions = {
        r[0]
        for r in pg_db.execute(
            text(
                "SELECT action FROM access_audit_logs WHERE entity_type = 'edge_controller' "
                "AND entity_id = :e"
            ),
            {"e": str(cid)},
        ).all()
    }
    assert "access.controller_create" in actions
    assert "access.controller_rotate_key" in actions
    # Секрет/ключ НЕ попадает в детали аудита (§11).
    details = pg_db.execute(
        text(
            "SELECT details::text FROM access_audit_logs WHERE entity_type='edge_controller' "
            "AND entity_id = :e"
        ),
        {"e": str(cid)},
    ).all()
    for (d,) in details:
        assert "api_key" not in (d or "")


# ------------------------------ multi-point independence ------------------------------


def test_multipoint_two_zones_two_controllers_independent(pg_db) -> None:
    """Мультиточечность: 2 зоны/2 контроллера независимы, оба проходят device-auth."""
    uid = _u(pg_db, "system_admin")
    c = _client(uid, "system_admin")

    z1 = _create_zone(c)
    z2 = _create_zone(c)
    assert z1["id"] != z2["id"]

    uid1, uid2 = _new_uid(), _new_uid()
    k1 = c.post(
        "/api/v1/access/admin/controllers",
        json={"controller_uid": uid1, "zone_id": z1["id"]},
    ).json()["api_key"]
    k2 = c.post(
        "/api/v1/access/admin/controllers",
        json={"controller_uid": uid2, "zone_id": z2["id"]},
    ).json()["api_key"]

    # Каждый контроллер аутентифицируется только своим ключом (изоляция).
    assert _edge_get(uid1, k1) == 204
    assert _edge_get(uid2, k2) == 204
    assert _edge_get(uid1, k2) == 401  # чужой ключ
    assert _edge_get(uid2, k1) == 401
