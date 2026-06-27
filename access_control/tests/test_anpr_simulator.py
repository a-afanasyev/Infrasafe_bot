"""ANPR-симулятор (§14.2 п.4): синтетические события с валидной device-auth подписью.

Симулятор генерит синтетические ANPR-события (§11 — только синтетика) и шлёт их на
``/camera-events/anpr`` с корректной device-auth подписью (тот же канонический
стринг/HMAC, что и backend). Используется для e2e-проверки полного контура.

PostgreSQL-only.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from access_control.app.main import create_app
from access_control.edge.anpr_simulator import AnprSimulator
from access_control.tests.conftest import PilotFixture, seed_permanent_vehicle


def _simulator(pilot: PilotFixture) -> AnprSimulator:
    return AnprSimulator(
        TestClient(create_app()),
        controller_uid=pilot.controller_uid,
        zone_id=pilot.zone_id,
        gate_id=pilot.gate_id,
        camera_id=pilot.camera_id,
        barrier_id=pilot.barrier_id,
    )


def test_simulator_passes_device_auth_and_gets_decision(
    pg_db, pilot: PilotFixture
) -> None:
    """Симулятор подписывает событие → device-auth проходит → движок выдаёт решение."""
    seed_permanent_vehicle(pg_db, pilot, normalized="01A001AA")
    sim = _simulator(pilot)
    resp = sim.send(plate="01A001AA", event_id="sim-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "allow"
    assert body["command"] is not None


def test_simulator_unknown_plate_denied(pg_db, pilot: PilotFixture) -> None:
    """Неизвестный синтетический номер → deny, без открытия шлагбаума."""
    sim = _simulator(pilot)
    resp = sim.send(plate="07X321XX", event_id="sim-2")
    assert resp.status_code == 200
    out = resp.json()
    assert out["decision"] == "deny"
    assert out["command"] is None


def test_simulator_generates_synthetic_plate(pg_db, pilot: PilotFixture) -> None:
    """random_plate отдаёт синтетический номер (§11): детерминированный формат."""
    sim = _simulator(pilot)
    plate = sim.random_plate()
    assert isinstance(plate, str) and len(plate) >= 6


def test_simulator_build_event_shape(pg_db, pilot: PilotFixture) -> None:
    """build_event формирует валидный ANPR-DTO с captured_at и controller_uid."""
    sim = _simulator(pilot)
    event = sim.build_event("01A001AA", event_id="sim-3")
    assert event["controller_uid"] == pilot.controller_uid
    assert event["event_id"] == "sim-3"
    assert event["plate_number"] == "01A001AA"
    assert "captured_at" in event
