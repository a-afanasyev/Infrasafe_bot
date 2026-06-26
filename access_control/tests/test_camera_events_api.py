"""Тесты endpoint POST /api/v1/access/camera-events/anpr (§13.1).

Endpoint вызывает ingestion и возвращает решение (+ команду для allow,
fast-path заготовка §9.2). Device-auth — тонкая заглушка ``verify_device``
(проверка наличия edge_controller по controller_uid; HMAC/nonce — Ф6).

Endpoint использует синхронный get_db (postgres в контейнере); сидинг — через
pg_db (тот же DATABASE_URL), коммит виден сессии запроса.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from access_control.app.main import create_app
from access_control.tests.conftest import (
    SigningClient,
    seed_permanent_vehicle,
    utcnow,
)


def _body(pilot, *, controller_uid, event_id, plate):
    return {
        "controller_uid": controller_uid,
        "event_id": event_id,
        "zone_id": pilot.zone_id,
        "gate_id": pilot.gate_id,
        "camera_id": pilot.camera_id,
        "barrier_id": pilot.barrier_id,
        "plate_number": plate,
        "direction": "entry",
        "confidence": 0.95,
        "captured_at": utcnow().isoformat(),
    }


def test_anpr_endpoint_allows_permanent_vehicle(pg_db, pilot) -> None:
    seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA")
    client = SigningClient(TestClient(create_app()), pilot.controller_uid)
    resp = client.post(
        "/api/v1/access/camera-events/anpr",
        json=_body(
            pilot, controller_uid=pilot.controller_uid, event_id="api-1", plate="01A001AA"
        ),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "allow"
    assert body["reason"] == "permanent_vehicle_allowed"
    assert body["command"] is not None
    assert body["command"]["barrier_id"] == pilot.barrier_id


def test_anpr_endpoint_unknown_device_rejected(pg_db, pilot) -> None:
    # Подписываем как несуществующий контроллер → device-auth не найдёт его → 401.
    client = SigningClient(TestClient(create_app()), "ctrl-does-not-exist")
    resp = client.post(
        "/api/v1/access/camera-events/anpr",
        json=_body(
            pilot, controller_uid="ctrl-does-not-exist", event_id="api-2", plate="01A001AA"
        ),
    )
    assert resp.status_code == 401


def test_anpr_router_registered() -> None:
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/api/v1/access/camera-events/anpr" in paths
