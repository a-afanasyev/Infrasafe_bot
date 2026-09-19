"""AUD8-SEC-02: rate-limit на резидентских write-эндпоинтах (PostgreSQL-only).

POST /requests и POST /passes у applicant'а не были ограничены: скомпрометированный
аккаунт мог за минуту создать тысячи pending-заявок (очередь менеджера) или
гостевых кодов. Лимит — per-user фиксированное окно на том же стор-бэкенде, что
lockout кодов (in-memory в тестах, Redis в проде, fail-closed).
"""
from __future__ import annotations

import datetime as dt
import types

import pytest
from fastapi.testclient import TestClient

from access_control.app.main import create_app
from access_control.services import action_rate_limit
from access_control.services.code_rate_limit import (
    InMemoryFailureStore,
    reset_failure_store,
)
from access_control.tests.conftest import PilotFixture, seed_user, utcnow
from access_control.tests.test_resident_api import (
    _link_user_apartment,
    _link_zone_yard,
    _yard_of,
)
from uk_management_bot.api.dependencies import get_current_user


def _fake_user(uid: int, role: str = "applicant"):
    import json

    return lambda: types.SimpleNamespace(
        id=uid, roles=json.dumps([role]), active_role=role, status="approved"
    )


def _client(uid: int) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid)
    return TestClient(app)


def _seed_resident(pg_db, pilot: PilotFixture) -> int:
    uid = seed_user(pg_db, roles="applicant")
    _link_user_apartment(pg_db, uid, pilot.apartment_id, "approved")
    _link_zone_yard(pg_db, pilot.zone_id, _yard_of(pg_db, pilot.apartment_id))
    return uid


@pytest.fixture(autouse=True)
def _fresh_store(monkeypatch):
    reset_failure_store(InMemoryFailureStore())
    monkeypatch.setattr(action_rate_limit, "RESIDENT_WRITE_LIMIT", 3)
    yield
    reset_failure_store(InMemoryFailureStore())


def _request_body(pilot: PilotFixture, i: int) -> dict:
    return {
        "apartment_id": pilot.apartment_id,
        "plate_number_original": f"01A{100 + i}BC",
        "relation_type": "owner",
    }


def _pass_body(pilot: PilotFixture) -> dict:
    return {
        "apartment_id": pilot.apartment_id,
        "pass_type": "guest",
        "valid_until": (utcnow() + dt.timedelta(hours=2)).isoformat(),
        "zone_id": pilot.zone_id,
    }


def test_requests_limited_per_user_then_429_with_retry_after(pg_db, pilot) -> None:
    uid = _seed_resident(pg_db, pilot)
    client = _client(uid)
    for i in range(3):
        r = client.post("/api/v1/access/requests", json=_request_body(pilot, i))
        assert r.status_code == 201, r.text
    r4 = client.post("/api/v1/access/requests", json=_request_body(pilot, 99))
    assert r4.status_code == 429
    assert r4.json()["detail"] == {"error": "too_many_requests"}
    assert int(r4.headers["Retry-After"]) > 0


def test_passes_limited_independently_and_per_user(pg_db, pilot) -> None:
    uid = _seed_resident(pg_db, pilot)
    client = _client(uid)
    # Лимит заявок исчерпан — пропуска это не касается (отдельный ключ).
    for i in range(3):
        assert client.post("/api/v1/access/requests", json=_request_body(pilot, i)).status_code == 201
    assert client.post("/api/v1/access/requests", json=_request_body(pilot, 9)).status_code == 429
    for _ in range(3):
        assert client.post("/api/v1/access/passes", json=_pass_body(pilot)).status_code == 201
    assert client.post("/api/v1/access/passes", json=_pass_body(pilot)).status_code == 429
    # Другой житель — свой счётчик.
    other = _seed_resident(pg_db, pilot)
    assert _client(other).post("/api/v1/access/passes", json=_pass_body(pilot)).status_code == 201


def test_rejected_attempts_do_not_consume_quota_of_ownership_check(pg_db, pilot) -> None:
    """403 (чужая квартира) не должен считаться раньше лимита? Нет: лимит
    считает ПОПЫТКИ — иначе перебор чужих apartment_id бесплатен."""
    uid = seed_user(pg_db, roles="applicant")  # без владения
    client = _client(uid)
    for _ in range(3):
        assert client.post("/api/v1/access/requests", json=_request_body(pilot, 1)).status_code == 403
    assert client.post("/api/v1/access/requests", json=_request_body(pilot, 1)).status_code == 429
