"""ADMIN-эндпоинт диагностики точки въезда: синтетический ANPR через Decision Engine.

Замена камеры для приёмки (§6.1, §7, §11, §15): ``system_admin`` шлёт синтетическое
ANPR-событие на контроллер серверно (без device-auth), оно проходит ТОТ ЖЕ
Decision Engine, что и реальное событие с камеры — пишет
camera_events/access_decisions/access_events, при allow создаёт barrier_command.

Проверяем:
* RBAC: system_admin 200; manager/security_operator/applicant → 403; без auth → 401;
* сконфигурированная точка + постоянное авто (DIAG-номер привязан) → allow + команда;
* неизвестный номер → deny vehicle_not_found, команды нет;
* событие реально пишется в camera_events (event_id ``diag-`` + attributes.diagnostic);
* аудит-запись ``access.diagnostic_test_event`` создаётся (без номера в details);
* контроллер без gate/barrier → НЕ 500 (диагностика показывает проблему конфигурации).
PostgreSQL-only (как и весь ingestion).
"""
from __future__ import annotations

import types
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.tests.conftest import (
    PilotFixture,
    seed_permanent_vehicle,
    seed_user,
)
from uk_management_bot.api.dependencies import get_current_user

DIAG_PLATE = "DIAG0001"


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


def _u(db, role: str) -> int:
    return seed_user(db, roles=role)


def _path(controller_id: int) -> str:
    return f"/api/v1/access/admin/controllers/{controller_id}/test-event"


def _bare_controller(c: TestClient) -> int:
    """Контроллер с зоной, но БЕЗ gate/barrier — для проверки неполной конфигурации."""
    zone = c.post(
        "/api/v1/access/admin/zones",
        json={"code": f"z-{uuid.uuid4().hex[:6]}", "name": "Зона"},
    )
    assert zone.status_code == 201, zone.text
    ctrl = c.post(
        "/api/v1/access/admin/controllers",
        json={"controller_uid": f"diag-ctrl-{uuid.uuid4().hex[:8]}",
              "zone_id": zone.json()["id"]},
    )
    assert ctrl.status_code == 201, ctrl.text
    return ctrl.json()["id"]


# ------------------------------ router wiring ------------------------------


def test_diagnostics_router_registered() -> None:
    paths = {route.path for route in create_app().routes}
    assert "/api/v1/access/admin/controllers/{controller_id}/test-event" in paths


# ------------------------------ RBAC ------------------------------


def test_test_event_requires_auth_401(pg_db, pilot: PilotFixture) -> None:
    resp = TestClient(create_app()).post(_path(pilot.controller_id), json={})
    assert resp.status_code == 401


def test_test_event_manager_403(pg_db, pilot: PilotFixture) -> None:
    uid = _u(pg_db, "manager")
    assert _client(uid, "manager").post(_path(pilot.controller_id), json={}).status_code == 403


def test_test_event_security_operator_403(pg_db, pilot: PilotFixture) -> None:
    uid = _u(pg_db, "security_operator")
    assert (
        _client(uid, "security_operator").post(_path(pilot.controller_id), json={}).status_code
        == 403
    )


def test_test_event_applicant_403(pg_db, pilot: PilotFixture) -> None:
    uid = _u(pg_db, "applicant")
    assert _client(uid, "applicant").post(_path(pilot.controller_id), json={}).status_code == 403


def test_test_event_system_admin_200(pg_db, pilot: PilotFixture) -> None:
    uid = _u(pg_db, "system_admin")
    resp = _client(uid, "system_admin").post(_path(pilot.controller_id), json={})
    assert resp.status_code == 200, resp.text


def test_test_event_unknown_controller_404(pg_db) -> None:
    uid = _u(pg_db, "system_admin")
    resp = _client(uid, "system_admin").post(_path(999999), json={})
    assert resp.status_code == 404


# ------------------------------ allow на сконфигурированной точке ------------------------------


def test_configured_point_permanent_vehicle_allows_and_creates_command(
    pg_db, pilot: PilotFixture
) -> None:
    """Постоянное авто привязано к зоне точки → allow + команда открытия создана."""
    seed_permanent_vehicle(pg_db, pilot, normalized=DIAG_PLATE)
    uid = _u(pg_db, "system_admin")
    resp = _client(uid, "system_admin").post(
        _path(pilot.controller_id), json={"plate_number": DIAG_PLATE}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"] == "allow"
    assert body["status"] == "allowed"
    assert body["zone_id"] == pilot.zone_id
    assert body["gate_id"] == pilot.gate_id
    assert body["barrier_id"] == pilot.barrier_id
    assert body["event_id"].startswith("diag-")
    assert body["command"] is not None
    assert body["command"]["barrier_id"] == pilot.barrier_id
    assert body["command"]["command_id"]

    # Команда реально записана в barrier_commands под decision этого события.
    cmd = pg_db.execute(
        text(
            "SELECT barrier_id FROM barrier_commands WHERE decision_id = :d"
        ),
        {"d": body["decision_id"]},
    ).first()
    assert cmd is not None
    assert cmd[0] == pilot.barrier_id


# ------------------------------ deny на неизвестном номере ------------------------------


def test_unknown_plate_denies_and_no_command(pg_db, pilot: PilotFixture) -> None:
    uid = _u(pg_db, "system_admin")
    resp = _client(uid, "system_admin").post(
        _path(pilot.controller_id), json={"plate_number": "NOSUCH999"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["decision"] == "deny"
    assert body["reason"] == "vehicle_not_found"
    assert body["command"] is None
    # Команда НЕ создана.
    n = pg_db.execute(
        text("SELECT count(*) FROM barrier_commands WHERE decision_id = :d"),
        {"d": body["decision_id"]},
    ).scalar_one()
    assert n == 0


# ------------------------------ событие реально пишется ------------------------------


def test_event_persisted_with_diag_prefix_and_diagnostic_flag(
    pg_db, pilot: PilotFixture
) -> None:
    uid = _u(pg_db, "system_admin")
    resp = _client(uid, "system_admin").post(_path(pilot.controller_id), json={})
    assert resp.status_code == 200, resp.text
    event_id = resp.json()["event_id"]
    row = pg_db.execute(
        text(
            "SELECT event_id, attributes, controller_id, source FROM camera_events "
            "WHERE event_id = :e"
        ),
        {"e": event_id},
    ).mappings().first()
    assert row is not None
    assert row["event_id"].startswith("diag-")
    assert row["controller_id"] == pilot.controller_id
    assert row["source"] == "connected"
    assert (row["attributes"] or {}).get("diagnostic") is True


# ------------------------------ аудит ------------------------------


def test_test_event_writes_audit_without_plate(pg_db, pilot: PilotFixture) -> None:
    uid = _u(pg_db, "system_admin")
    resp = _client(uid, "system_admin").post(
        _path(pilot.controller_id), json={"plate_number": DIAG_PLATE}
    )
    assert resp.status_code == 200, resp.text
    rows = pg_db.execute(
        text(
            "SELECT actor_user_id, details::text, row_hash FROM access_audit_logs "
            "WHERE action = 'access.diagnostic_test_event' "
            "AND entity_type = 'edge_controller' AND entity_id = :e"
        ),
        {"e": str(pilot.controller_id)},
    ).all()
    assert len(rows) == 1
    actor, details, row_hash = rows[0]
    assert actor == uid
    assert row_hash is not None  # hash-chain заполнен
    # §11: синтетический/реальный номер в details НЕ пишется.
    assert DIAG_PLATE not in (details or "")
    assert "plate" not in (details or "")


# ------------------------------ неполная конфигурация точки ------------------------------


def test_controller_without_gate_or_barrier_not_500(pg_db) -> None:
    """Контроллер без активного gate/barrier → НЕ 500: диагностика показывает проблему."""
    uid = _u(pg_db, "system_admin")
    c = _client(uid, "system_admin")
    cid = _bare_controller(c)
    resp = c.post(_path(cid), json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["gate_id"] is None
    assert body["barrier_id"] is None
    assert body["command"] is None
    assert body["decision"] in ("allow", "deny", "manual_review")
