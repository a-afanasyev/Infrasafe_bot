"""Тесты health/latency-метрик (§10.2, §14.2 п.17, критерий §15.16).

Покрывают:
* раздельную запись latency по фазам ingestion/decision/db/relay (§10.2);
* доступность метрик через эндпоинты ``/metrics`` (prometheus) и
  ``/api/v1/access/metrics`` (JSON);
* отсутствие ПД (§11) в выводе метрик — номер автомобиля не попадает ни в
  prometheus-текст, ни в JSON;
* §15.16 latency budget — одиночное решение укладывается в (мягкий на CI)
  бюджет, а измерение собрано РАЗДЕЛЬНО по фазам.

Unit-часть (LatencyRegistry/percentiles) — БД-независима; интеграционная часть
(ingestion/эндпоинты) требует postgres (как остальной ingestion-набор).
"""
from __future__ import annotations

import json
import os
import types

from fastapi.testclient import TestClient

import access_control.services.metrics as metrics
from access_control.app.main import create_app
from access_control.integrations.relay import MockRelay, RelayCommand
from access_control.services.ingestion import AnprIngestInput, ingest_anpr
from access_control.tests.conftest import (
    SigningClient,
    seed_permanent_vehicle,
    utcnow,
)
from uk_management_bot.api.dependencies import get_current_user


def _authed_client(role: str, status: str = "approved") -> TestClient:
    """TestClient с подменённым USER-API актором (SEC-04: JSON-метрики под RBAC)."""
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: types.SimpleNamespace(
        id=1, roles=json.dumps([role]), active_role=role, status=status
    )
    return TestClient(app)

# Мягкий бюджет одиночного решения для CI (§15.16): локальная сеть пилота
# укладывается в 500 мс (decision-p95 §10.2), но CI-раннер существенно медленнее —
# порог конфигурируем, дефолт щедрый. Раздельность измерения проверяется жёстко.
_SINGLE_DECISION_BUDGET_MS = float(os.getenv("ACCESS_LATENCY_TEST_BUDGET_MS", "2000"))


# ── Unit: LatencyRegistry/percentiles (без БД) ───────────────────────────────
def test_latency_registry_percentiles() -> None:
    reg = metrics.LatencyRegistry(maxlen=1000)
    for ms in range(1, 101):  # 1..100 мс
        reg.observe(metrics.PHASE_DECISION, float(ms))
    s = reg.stats(metrics.PHASE_DECISION)
    assert s.count == 100
    assert s.max_ms == 100.0
    # nearest-rank: p50≈50, p95≈95, p99≈99 (±1 из-за округления ранга).
    assert 49.0 <= s.p50_ms <= 51.0
    assert 94.0 <= s.p95_ms <= 96.0
    assert 98.0 <= s.p99_ms <= 100.0


def test_latency_registry_empty_phase_is_zero() -> None:
    reg = metrics.LatencyRegistry()
    s = reg.stats(metrics.PHASE_RELAY)
    assert s.count == 0
    assert s.p95_ms == 0.0 and s.max_ms == 0.0


def test_relay_open_records_relay_latency() -> None:
    metrics.reset_latency_registry()
    relay = MockRelay()
    relay.open(RelayCommand(command_id="cmd-metrics-1", barrier_id=7))
    # Повтор того же command_id — дедуп, латентность НЕ должна записаться второй раз.
    relay.open(RelayCommand(command_id="cmd-metrics-1", barrier_id=7))
    s = metrics.get_latency_registry().stats(metrics.PHASE_RELAY)
    assert s.count == 1


def test_budget_report_structure_within_budget_when_fast() -> None:
    metrics.reset_latency_registry()
    metrics.observe_decision(10.0)  # быстрее бюджета
    metrics.observe_relay(20.0)
    report = metrics.budget_report()
    assert report["within_budget"] is True
    assert report["breaches"] == []
    assert report["budgets_ms"]["decision_p95"] == metrics.DECISION_P95_BUDGET_MS
    assert report["budgets_ms"]["relay_p95"] == metrics.EDGE_RELAY_P95_BUDGET_MS


def test_budget_report_flags_decision_breach() -> None:
    metrics.reset_latency_registry()
    metrics.observe_decision(metrics.DECISION_P95_BUDGET_MS + 100.0)
    report = metrics.budget_report()
    assert report["within_budget"] is False
    assert "decision_p95" in report["breaches"]


# ── Интеграция: ingestion записывает раздельные фазы (postgres) ───────────────
def test_ingestion_records_separate_phase_latencies(pg_db, pilot) -> None:
    metrics.reset_latency_registry()
    seed_permanent_vehicle(pg_db, pilot, normalized="01M001MM")
    res = ingest_anpr(
        pg_db,
        AnprIngestInput(
            controller_id=pilot.controller_id,
            event_id="metrics-evt-1",
            zone_id=pilot.zone_id,
            gate_id=pilot.gate_id,
            camera_id=pilot.camera_id,
            barrier_id=pilot.barrier_id,
            plate_number_original="01M001MM",
            direction="entry",
            confidence=0.95,
            captured_at=utcnow(),
        ),
    )
    assert res.decision == "allow"
    reg = metrics.get_latency_registry()
    # §10.2: ingestion, decision и db измерены РАЗДЕЛЬНО (каждая фаза — ≥1 сэмпл).
    assert reg.stats(metrics.PHASE_INGESTION).count >= 1
    assert reg.stats(metrics.PHASE_DECISION).count >= 1
    assert reg.stats(metrics.PHASE_DB).count >= 1


# ── §15.16 latency budget ────────────────────────────────────────────────────
def test_criterion16_single_decision_within_budget(pg_db, pilot) -> None:
    """§15.16: одиночное решение укладывается в (мягкий) бюджет, измерено раздельно."""
    metrics.reset_latency_registry()
    seed_permanent_vehicle(pg_db, pilot, normalized="01B016BB")
    ingest_anpr(
        pg_db,
        AnprIngestInput(
            controller_id=pilot.controller_id,
            event_id="budget-evt-1",
            zone_id=pilot.zone_id,
            gate_id=pilot.gate_id,
            camera_id=pilot.camera_id,
            barrier_id=pilot.barrier_id,
            plate_number_original="01B016BB",
            direction="entry",
            confidence=0.95,
            captured_at=utcnow(),
        ),
    )
    decision = metrics.get_latency_registry().stats(metrics.PHASE_DECISION)
    assert decision.count >= 1, "decision-фаза должна быть измерена отдельно (§10.2)"
    # Мягкий порог для CI; раздельное измерение decision собрано и сравнивается.
    assert decision.p95_ms <= _SINGLE_DECISION_BUDGET_MS, (
        f"decision p95={decision.p95_ms}мс > бюджет {_SINGLE_DECISION_BUDGET_MS}мс "
        "(на локальной сети пилота бюджет §10.2 = 500мс; CI-порог мягче)"
    )


# ── Эндпоинты метрик + PD-safe (§11) ─────────────────────────────────────────
def test_prometheus_endpoint_exposes_phase_latency(pg_db, pilot) -> None:
    metrics.reset_latency_registry()
    seed_permanent_vehicle(pg_db, pilot, normalized="01P001PP")
    client = SigningClient(TestClient(create_app()), pilot.controller_uid)
    client.post(
        "/api/v1/access/camera-events/anpr",
        json={
            "controller_uid": pilot.controller_uid,
            "event_id": "prom-evt-1",
            "zone_id": pilot.zone_id,
            "gate_id": pilot.gate_id,
            "camera_id": pilot.camera_id,
            "barrier_id": pilot.barrier_id,
            "plate_number": "01P001PP",
            "direction": "entry",
            "confidence": 0.95,
            "captured_at": utcnow().isoformat(),
        },
    )
    resp = TestClient(create_app()).get("/metrics")
    assert resp.status_code == 200
    assert "access_phase_latency_seconds" in resp.text


def test_json_metrics_endpoint_returns_phases_and_budget(pg_db, pilot) -> None:
    resp = _authed_client("manager").get("/api/v1/access/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert "phases" in body
    assert "budget" in body
    assert "within_budget" in body["budget"]
    assert "queue" in body


# ── SEC-04: RBAC на JSON-метриках (Prometheus-текст остаётся internal) ─────────
def test_json_metrics_requires_auth_401(pg_db, pilot) -> None:
    """Без auth JSON-сводка недоступна (раскрывала инвентарь контроллеров/бэклог)."""
    resp = TestClient(create_app()).get("/api/v1/access/metrics")
    assert resp.status_code == 401


def test_json_metrics_forbidden_for_non_manager_403(pg_db, pilot) -> None:
    """applicant/security_operator и пр. → 403 на JSON-метриках."""
    assert _authed_client("applicant").get("/api/v1/access/metrics").status_code == 403
    assert _authed_client("security_operator").get(
        "/api/v1/access/metrics"
    ).status_code == 403


def test_json_metrics_system_admin_allowed(pg_db, pilot) -> None:
    resp = _authed_client("system_admin").get("/api/v1/access/metrics")
    assert resp.status_code == 200


def test_prometheus_metrics_stays_open_for_internal_scrape(pg_db, pilot) -> None:
    """Prometheus-текст (/metrics) НЕ гейтится — скрейпит внутренний Prometheus."""
    resp = TestClient(create_app()).get("/metrics")
    assert resp.status_code == 200


def test_metrics_output_contains_no_plate_number_pd(pg_db, pilot) -> None:
    """§11: номер автомобиля не должен попадать в метки/вывод метрик."""
    metrics.reset_latency_registry()
    secret_plate = "01PD777DP"
    seed_permanent_vehicle(pg_db, pilot, normalized=secret_plate)
    client = SigningClient(TestClient(create_app()), pilot.controller_uid)
    client.post(
        "/api/v1/access/camera-events/anpr",
        json={
            "controller_uid": pilot.controller_uid,
            "event_id": "pd-evt-1",
            "zone_id": pilot.zone_id,
            "gate_id": pilot.gate_id,
            "camera_id": pilot.camera_id,
            "barrier_id": pilot.barrier_id,
            "plate_number": secret_plate,
            "direction": "entry",
            "confidence": 0.95,
            "captured_at": utcnow().isoformat(),
        },
    )
    # Ни prometheus-текст, ни JSON-сводка не содержат номер автомобиля (§11).
    prom = TestClient(create_app()).get("/metrics").text
    js = json.dumps(_authed_client("manager").get("/api/v1/access/metrics").json())
    assert secret_plate not in prom
    assert secret_plate not in js
    # И прямой сериализатор реестра тоже PD-safe.
    assert secret_plate not in metrics.prometheus_text().decode("utf-8")
