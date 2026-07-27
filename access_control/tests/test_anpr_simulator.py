"""ANPR-симулятор (§14.2 п.4): синтетические события с валидной device-auth подписью.

Симулятор генерит синтетические ANPR-события (§11 — только синтетика) и шлёт их на
``/camera-events/anpr`` с корректной device-auth подписью (тот же канонический
стринг/HMAC, что и backend). Используется для e2e-проверки полного контура.

PostgreSQL-only.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from access_control.app.main import create_app
from access_control.edge import anpr_simulator
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
        api_key=pilot.api_key,
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


class TestApiKeyHasNoBakedDefault:
    """AUD5-SEC-NEW-4: ключ устройства не должен приезжать из репозитория.

    Раньше конструктор нёс `api_key="pilot-test-device-key"`. Само по себе это
    значение эксплуатируемо только если симулятор запущен против стенда, где
    такой ключ провижинен, — но именно поэтому дефолт и опасен: запуск против
    живого контура выглядел бы штатным, а ключ брался бы из исходников.

    Проверяется наблюдаемое следствие (конструктор не собирается без ключа), а
    не форма записи — переименование параметра тест не обманет.
    """

    def test_construction_without_api_key_fails(self) -> None:
        with pytest.raises(TypeError):
            AnprSimulator(
                object(),
                controller_uid="ctrl-1",
                zone_id=1,
                gate_id=1,
                camera_id=1,
                barrier_id=1,
            )

    def test_module_carries_no_key_literal_in_code(self) -> None:
        """Дефолт не должен вернуться и в виде модульной константы.

        Проверка по AST, а не по подстроке: docstring этого же класса объясняет,
        какое именно значение было зашито, и наивный поиск ловил бы объяснение
        вместо кода — ровно тот ложный сигнал, из-за которого «гейт сработал»
        и «гейт поймал сам себя» неразличимы.
        """
        tree = ast.parse(Path(anpr_simulator.__file__).read_text(encoding="utf-8"))
        docstrings = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
        }
        offenders = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and node not in docstrings
            and isinstance(node.value, str)
            and "device-key" in node.value
        ]
        assert not offenders, f"ключ устройства снова зашит в код, строки: {offenders}"
