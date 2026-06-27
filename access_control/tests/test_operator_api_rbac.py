"""Ф5: RBAC + HTTP-контракт operator API (§6.3, §13.2). PostgreSQL-only.

Покрывает критерий приёмки §15:
* 7: нет auth → 401; чужая роль (executor) → 403; пустой reason → 422;
  успешный manual_open фиксирует operator_user_id и reason;
* 8: прямой manual-open при активном pending_review → 409 + event_id;
* 19 (часть): пользователь без нужной роли не получает operator API.

Auth — существующая JWT/cookie (get_current_user); в тесте dependency override
подставляет аутентифицированного пользователя с заданной ролью, что прогоняет
реальную проверку require_roles. 401-кейс идёт БЕЗ override (реальный 401).
"""
from __future__ import annotations

import types

from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.tests.conftest import (
    PilotFixture,
    seed_pending_review,
    seed_user,
)
from uk_management_bot.api.dependencies import get_current_user


def _fake_user(uid: int, role: str, status: str = "approved"):
    import json

    return lambda: types.SimpleNamespace(
        id=uid, roles=json.dumps([role]), active_role=role, status=status
    )


def test_resolve_requires_auth_401(pg_db, pilot: PilotFixture) -> None:
    pending = seed_pending_review(pg_db, pilot)
    client = TestClient(create_app())
    resp = client.post(
        f"/api/v1/access/events/{pending.camera_event_id}/resolve",
        json={"action": "deny", "reason": "x", "barrier_id": pilot.barrier_id,
              "decision_id": pending.decision_id},
    )
    assert resp.status_code == 401


def test_manual_open_requires_auth_401(pg_db, pilot: PilotFixture) -> None:
    client = TestClient(create_app())
    resp = client.post(
        f"/api/v1/access/barriers/{pilot.barrier_id}/manual-open",
        json={"reason": "x", "source": "emergency"},
    )
    assert resp.status_code == 401


def test_manual_open_forbidden_role_403(pg_db, pilot: PilotFixture) -> None:
    """Критерий 7/19: executor не имеет доступа → 403."""
    uid = seed_user(pg_db, roles="executor")
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "executor")
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/access/barriers/{pilot.barrier_id}/manual-open",
        json={"reason": "x", "source": "emergency"},
    )
    assert resp.status_code == 403


def test_manual_open_empty_reason_422(pg_db, pilot: PilotFixture) -> None:
    """Критерий 7: пустая причина → 422."""
    uid = seed_user(pg_db, roles="security_operator")
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "security_operator")
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/access/barriers/{pilot.barrier_id}/manual-open",
        json={"reason": "", "source": "emergency"},
    )
    assert resp.status_code == 422


def test_manual_open_success_records_operator(pg_db, pilot: PilotFixture) -> None:
    """Критерий 7: успешный manual_open фиксирует operator_user_id и reason."""
    uid = seed_user(pg_db, roles="security_operator")
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "security_operator")
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/access/barriers/{pilot.barrier_id}/manual-open",
        json={"reason": "плановая проверка", "source": "tech_check"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["command_id"] is not None
    row = pg_db.execute(
        text(
            "SELECT operator_user_id, reason FROM manual_openings WHERE barrier_id = :b"
        ),
        {"b": pilot.barrier_id},
    ).first()
    assert row[0] == uid
    assert row[1] == "плановая проверка"


def test_manual_open_conflict_409_with_event_id(pg_db, pilot: PilotFixture) -> None:
    """Критерий 8: manual-open при активном pending → 409 + event_id, без команды."""
    uid = seed_user(pg_db, roles="manager")
    pending = seed_pending_review(pg_db, pilot)
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "manager")
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/access/barriers/{pilot.barrier_id}/manual-open",
        json={"reason": "x", "source": "emergency"},
    )
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["event_id"] == pending.camera_event_id
    cnt = pg_db.execute(
        text("SELECT count(*) FROM barrier_commands WHERE barrier_id = :b"),
        {"b": pilot.barrier_id},
    ).scalar()
    assert cnt == 0


def test_resolve_manual_open_success_http(pg_db, pilot: PilotFixture) -> None:
    """Критерий 9(a) через HTTP: resolve manual_open → allowed_manually + команда."""
    uid = seed_user(pg_db, roles="security_operator")
    pending = seed_pending_review(pg_db, pilot)
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "security_operator")
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/access/events/{pending.camera_event_id}/resolve",
        json={"action": "manual_open", "reason": "ок", "barrier_id": pilot.barrier_id,
              "decision_id": pending.decision_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "allowed_manually"
    assert body["command_id"] is not None


def test_operator_router_registered() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/api/v1/access/events/{event_id}/resolve" in paths
    assert "/api/v1/access/barriers/{barrier_id}/manual-open" in paths


# --------------------- M1: оператор обязан быть approved ---------------------


def test_manual_open_operator_not_approved_403(pg_db, pilot: PilotFixture) -> None:
    """M1: роль есть (security_operator), но status != 'approved' → 403."""
    uid = seed_user(pg_db, roles="security_operator", status="pending")
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(
        uid, "security_operator", status="pending"
    )
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/access/barriers/{pilot.barrier_id}/manual-open",
        json={"reason": "x", "source": "emergency"},
    )
    assert resp.status_code == 403


def test_resolve_operator_not_approved_403(pg_db, pilot: PilotFixture) -> None:
    """M1: resolve endpoint тоже требует approved-оператора."""
    uid = seed_user(pg_db, roles="security_operator", status="pending")
    pending = seed_pending_review(pg_db, pilot)
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(
        uid, "security_operator", status="pending"
    )
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/access/events/{pending.camera_event_id}/resolve",
        json={"action": "deny", "reason": "x", "barrier_id": pilot.barrier_id,
              "decision_id": pending.decision_id},
    )
    assert resp.status_code == 403


# --------------- §15.19: RBAC-негатив + system_admin доступ ------------------


def test_inspector_forbidden_both_endpoints_403(pg_db, pilot: PilotFixture) -> None:
    """§15.19: inspector → 403 на обоих endpoint'ах."""
    uid = seed_user(pg_db, roles="inspector")
    pending = seed_pending_review(pg_db, pilot)
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "inspector")
    client = TestClient(app)
    r1 = client.post(
        f"/api/v1/access/barriers/{pilot.barrier_id}/manual-open",
        json={"reason": "x", "source": "emergency"},
    )
    r2 = client.post(
        f"/api/v1/access/events/{pending.camera_event_id}/resolve",
        json={"action": "deny", "reason": "x", "barrier_id": pilot.barrier_id,
              "decision_id": pending.decision_id},
    )
    assert r1.status_code == 403
    assert r2.status_code == 403


def test_applicant_forbidden_both_endpoints_403(pg_db, pilot: PilotFixture) -> None:
    """§15.19: applicant → 403 на обоих endpoint'ах."""
    uid = seed_user(pg_db, roles="applicant")
    pending = seed_pending_review(pg_db, pilot)
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "applicant")
    client = TestClient(app)
    r1 = client.post(
        f"/api/v1/access/barriers/{pilot.barrier_id}/manual-open",
        json={"reason": "x", "source": "emergency"},
    )
    r2 = client.post(
        f"/api/v1/access/events/{pending.camera_event_id}/resolve",
        json={"action": "deny", "reason": "x", "barrier_id": pilot.barrier_id,
              "decision_id": pending.decision_id},
    )
    assert r1.status_code == 403
    assert r2.status_code == 403


def test_system_admin_allowed_both_endpoints(pg_db, pilot: PilotFixture) -> None:
    """§15.19: system_admin (approved) имеет доступ — 200 на обоих endpoint'ах."""
    uid = seed_user(pg_db, roles="system_admin")
    pending = seed_pending_review(pg_db, pilot)
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "system_admin")
    client = TestClient(app)
    # resolve (deny) — без команды.
    r_resolve = client.post(
        f"/api/v1/access/events/{pending.camera_event_id}/resolve",
        json={"action": "deny", "reason": "админ-отказ", "barrier_id": pilot.barrier_id,
              "decision_id": pending.decision_id},
    )
    assert r_resolve.status_code == 200
    assert r_resolve.json()["status"] == "denied_manually"
    # manual-open (pending уже зарезолвен deny → активного pending нет) → 200.
    r_open = client.post(
        f"/api/v1/access/barriers/{pilot.barrier_id}/manual-open",
        json={"reason": "админ-открытие", "source": "tech_check"},
    )
    assert r_open.status_code == 200


# ------------------------ M5: decision_id mismatch 409 -----------------------


def test_resolve_decision_id_mismatch_409(pg_db, pilot: PilotFixture) -> None:
    """M5: переданный decision_id != текущего pending → 409 decision_id_mismatch."""
    uid = seed_user(pg_db, roles="security_operator")
    pending = seed_pending_review(pg_db, pilot)
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "security_operator")
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/access/events/{pending.camera_event_id}/resolve",
        json={"action": "manual_open", "reason": "ок", "barrier_id": pilot.barrier_id,
              "decision_id": pending.decision_id + 999},  # чужой decision_id
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "decision_id_mismatch"


# ------------------ M3/M4: barrier деактивирован → 4xx, не залип ---------------


def test_resolve_manual_open_barrier_deactivated_422(pg_db, pilot: PilotFixture) -> None:
    """M3/M4: barrier деактивирован после приёма → manual_open даёт 422, без NOT NULL.

    Pending не залипает: остаётся pending_review-строкой (append-only) и истечёт по
    deadline через worker (см. test_worker_expires_pending_with_deactivated_barrier).
    """
    from sqlalchemy import text as _text

    uid = seed_user(pg_db, roles="security_operator")
    pending = seed_pending_review(pg_db, pilot)
    pg_db.execute(
        _text("UPDATE access_barriers SET is_active = false WHERE id = :b"),
        {"b": pilot.barrier_id},
    )
    pg_db.commit()
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "security_operator")
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/access/events/{pending.camera_event_id}/resolve",
        json={"action": "manual_open", "reason": "ок", "barrier_id": pilot.barrier_id,
              "decision_id": pending.decision_id},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "barrier_unavailable"
    # Исходный pending не тронут (append-only, не залип в «вечный» переход).
    tip = pg_db.execute(
        _text("SELECT count(*) FROM access_decisions WHERE camera_event_id = :e"),
        {"e": pending.camera_event_id},
    ).scalar()
    assert tip == 1  # только исходный pending, перехода нет
    cmds = pg_db.execute(
        _text("SELECT count(*) FROM barrier_commands WHERE barrier_id = :b"),
        {"b": pilot.barrier_id},
    ).scalar()
    assert cmds == 0


# --------------------- §6.3: audit IP через HTTP-слой ------------------------


def test_manual_open_persists_client_ip(pg_db, pilot: PilotFixture) -> None:
    """§6.3: endpoint извлекает client.host и пишет его в access_audit_logs.ip_address."""
    uid = seed_user(pg_db, roles="security_operator")
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "security_operator")
    client = TestClient(app)
    resp = client.post(
        f"/api/v1/access/barriers/{pilot.barrier_id}/manual-open",
        json={"reason": "проверка", "source": "tech_check"},
    )
    assert resp.status_code == 200
    ip = pg_db.execute(
        text(
            "SELECT ip_address FROM access_audit_logs "
            "WHERE action = 'access.barrier_manual_open'"
        )
    ).scalar()
    assert ip is not None  # TestClient client.host (обычно 'testclient')
