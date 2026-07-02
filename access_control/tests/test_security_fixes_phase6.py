"""Security-фиксы Фазы 6 access_control: эксплойт-тесты (RED→GREEN).

Каждый тест фиксирует закрытие конкретной находки security-ревью Фазы 6:

* H1 — snapshot scope: валидно подписанный snapshot контроллера A, предъявленный
  верификатору контроллера B, должен быть отвергнут (controller_uid_mismatch).
* H2/M1 — нет хардкод-сидов: без env прод-путь подписи/HMAC даёт RuntimeError.
* M2 — redis nonce-store недоступен → FATAL (RuntimeError), без тихого отката.
* M3 — номер не попадает в логи даже на DEBUG (§11).
* M4 — обобщённый ответ 401 «unauthorized» (без enumeration unknown vs invalid key).
* M5 — доверенный прокси: IP берётся из X-Forwarded-For; чужой → 403, разрешённый → ок.

Юнит-части (H1/H2/M2) — без БД; endpoint-части (M3/M4/M5) — postgres-only (pilot).
"""
from __future__ import annotations

import logging

import pytest
from sqlalchemy import text

from access_control.edge.snapshot_verifier import SnapshotVerifier, verify_snapshot
from access_control.services.snapshot_signing import (
    build_snapshot,
    current_key_id,
    public_key_bytes,
    sign_snapshot,
)


def _signed_for(controller_uid: str) -> dict:
    snap = build_snapshot(controller_uid=controller_uid, zone_id=1)
    return sign_snapshot(snap).data


def _pinned() -> tuple[str, bytes]:
    return current_key_id(), public_key_bytes()


# ----------------------------- H1: snapshot scope -----------------------------


def test_snapshot_for_other_controller_rejected() -> None:
    """H1: валидно подписанный snapshot контроллера A у верификатора B → reject."""
    snap = _signed_for("ctrl-A")
    key_id, pub = _pinned()
    result = verify_snapshot(
        snap,
        pinned_key_id=key_id,
        pinned_public_key=pub,
        expected_controller_uid="ctrl-B",
    )
    assert result.accepted is False
    assert result.entry_allowed is False
    assert result.reason == "controller_uid_mismatch"


def test_snapshot_for_own_controller_accepted() -> None:
    """H1: snapshot своего контроллера со scope-проверкой принимается (entry всё равно нет)."""
    snap = _signed_for("ctrl-A")
    key_id, pub = _pinned()
    result = verify_snapshot(
        snap,
        pinned_key_id=key_id,
        pinned_public_key=pub,
        expected_controller_uid="ctrl-A",
    )
    assert result.accepted is True
    assert result.entry_allowed is False


def test_snapshot_verifier_scope_via_wrapper() -> None:
    """H1: stateful SnapshotVerifier, инициализированный UID своего контроллера, режет чужой."""
    snap = _signed_for("ctrl-A")
    key_id, pub = _pinned()
    verifier = SnapshotVerifier(key_id, pub, expected_controller_uid="ctrl-B")
    result = verifier.accept(snap)
    assert result.accepted is False
    assert result.reason == "controller_uid_mismatch"


# ----------------------- H2/M1: нет хардкод-сидов в коде -----------------------


def test_signing_seed_required_no_default(monkeypatch) -> None:
    """H2/M1: без ACCESS_SNAPSHOT_SIGNING_SEED подпись недоступна (RuntimeError)."""
    from access_control.services import snapshot_signing

    monkeypatch.delenv("ACCESS_SNAPSHOT_SIGNING_SEED", raising=False)
    with pytest.raises(RuntimeError):
        snapshot_signing.public_key_bytes()


def test_device_hmac_seed_required_no_default(monkeypatch) -> None:
    """H2/M1: без ACCESS_DEVICE_HMAC_SEED (и без per-device override) HMAC недоступен."""
    from access_control.services import device_auth

    monkeypatch.delenv("ACCESS_DEVICE_HMAC_SEED", raising=False)
    monkeypatch.delenv("ACCESS_DEVICE_SECRET__some-ctrl", raising=False)
    with pytest.raises(RuntimeError):
        device_auth.resolve_device_secret("some-ctrl")


def test_device_per_device_override_works_without_seed(monkeypatch) -> None:
    """M1: per-device ACCESS_DEVICE_SECRET__<ref> работает даже без общего сида."""
    from access_control.services import device_auth

    monkeypatch.delenv("ACCESS_DEVICE_HMAC_SEED", raising=False)
    monkeypatch.setenv("ACCESS_DEVICE_SECRET__ctrl-xyz", "per-device-secret")
    assert device_auth.resolve_device_secret("ctrl-xyz") == b"per-device-secret"


# ----------------------- M2: redis nonce-store FATAL -----------------------


def test_redis_nonce_store_unavailable_is_fatal(monkeypatch) -> None:
    """M2: backend=redis но redis недоступен → RuntimeError, без тихого in-memory отката."""
    import redis

    from access_control.services import device_auth

    class _BoomRedis:
        def ping(self):  # noqa: ANN001
            raise ConnectionError("redis down")

    monkeypatch.setenv("ACCESS_NONCE_BACKEND", "redis")
    monkeypatch.setattr(redis.Redis, "from_url", classmethod(lambda cls, *a, **k: _BoomRedis()))
    device_auth.reset_nonce_store(None)
    try:
        with pytest.raises(RuntimeError):
            device_auth.get_nonce_store()
    finally:
        device_auth.reset_nonce_store(device_auth.InMemoryNonceStore())


def test_memory_nonce_store_default_ok(monkeypatch) -> None:
    """M2: in-memory backend (дефолт) валиден и не падает."""
    from access_control.services import device_auth

    monkeypatch.setenv("ACCESS_NONCE_BACKEND", "memory")
    device_auth.reset_nonce_store(None)
    try:
        store = device_auth.get_nonce_store()
        assert isinstance(store, device_auth.InMemoryNonceStore)
    finally:
        device_auth.reset_nonce_store(device_auth.InMemoryNonceStore())


def test_nonce_backend_default_is_redis_in_prod(monkeypatch) -> None:
    """SEC-02: без ACCESS_NONCE_BACKEND и DEBUG=false дефолт → redis (fail-closed).

    Раньше отсутствие переменной означало ``memory`` — на multi-worker проде
    anti-replay становился process-local и replay проходил на другом воркере.
    Проверяем, что теперь прод-путь уходит в redis (недоступный redis → FATAL,
    что и подтверждает выбор redis-ветки, а не тихий in-memory).
    """
    import redis

    from access_control.services import device_auth
    from uk_management_bot.config.settings import settings

    class _BoomRedis:
        def ping(self):  # noqa: ANN001
            raise ConnectionError("redis down")

    monkeypatch.delenv("ACCESS_NONCE_BACKEND", raising=False)
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(redis.Redis, "from_url", classmethod(lambda cls, *a, **k: _BoomRedis()))
    device_auth.reset_nonce_store(None)
    try:
        with pytest.raises(RuntimeError):
            device_auth.get_nonce_store()
    finally:
        device_auth.reset_nonce_store(device_auth.InMemoryNonceStore())


def test_nonce_backend_default_is_memory_in_dev(monkeypatch) -> None:
    """SEC-02: без env и DEBUG=true дефолт → memory (dev-удобство сохранено)."""
    from access_control.services import device_auth
    from uk_management_bot.config.settings import settings

    monkeypatch.delenv("ACCESS_NONCE_BACKEND", raising=False)
    monkeypatch.setattr(settings, "DEBUG", True)
    device_auth.reset_nonce_store(None)
    try:
        assert isinstance(device_auth.get_nonce_store(), device_auth.InMemoryNonceStore)
    finally:
        device_auth.reset_nonce_store(device_auth.InMemoryNonceStore())


def test_failure_backend_default_is_redis_in_prod(monkeypatch) -> None:
    """SEC-02: lockout-счётчик — тот же fail-closed дефолт, что и nonce-store."""
    import redis

    from access_control.services import code_rate_limit
    from uk_management_bot.config.settings import settings

    class _BoomRedis:
        def ping(self):  # noqa: ANN001
            raise ConnectionError("redis down")

    monkeypatch.delenv("ACCESS_NONCE_BACKEND", raising=False)
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(redis.Redis, "from_url", classmethod(lambda cls, *a, **k: _BoomRedis()))
    code_rate_limit.reset_failure_store(None)
    try:
        with pytest.raises(RuntimeError):
            code_rate_limit.get_failure_store()
    finally:
        code_rate_limit.reset_failure_store(code_rate_limit.InMemoryFailureStore())


# ----------------------- SEC-03: Swagger fail-closed -----------------------


def test_docs_disabled_by_default_in_prod(monkeypatch) -> None:
    """SEC-03: без ACCESS_ENABLE_DOCS и DEBUG=false Swagger выключен (fail-closed).

    Раньше отсутствие переменной = включено → забытый env в проде раскрывал
    `/docs` `/redoc` `/openapi.json`. Теперь дефолт следует DEBUG.
    """
    from access_control.app import main
    from uk_management_bot.config.settings import settings

    monkeypatch.delenv("ACCESS_ENABLE_DOCS", raising=False)
    monkeypatch.setattr(settings, "DEBUG", False)
    assert main._docs_enabled() is False

    app = main.create_app()
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_docs_enabled_in_dev_by_default(monkeypatch) -> None:
    """SEC-03: в dev (DEBUG=true) Swagger по-прежнему включён без env."""
    from access_control.app import main
    from uk_management_bot.config.settings import settings

    monkeypatch.delenv("ACCESS_ENABLE_DOCS", raising=False)
    monkeypatch.setattr(settings, "DEBUG", True)
    assert main._docs_enabled() is True


def test_docs_explicit_env_overrides_debug(monkeypatch) -> None:
    """SEC-03: явный ACCESS_ENABLE_DOCS имеет высший приоритет над DEBUG."""
    from access_control.app import main
    from uk_management_bot.config.settings import settings

    # Явное «выкл» перебивает DEBUG=true
    monkeypatch.setattr(settings, "DEBUG", True)
    monkeypatch.setenv("ACCESS_ENABLE_DOCS", "0")
    assert main._docs_enabled() is False
    # Явное «вкл» перебивает DEBUG=false
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setenv("ACCESS_ENABLE_DOCS", "1")
    assert main._docs_enabled() is True


# ----------------------- endpoint-части (postgres-only) -----------------------


def _raw():
    from fastapi.testclient import TestClient

    from access_control.app.main import create_app

    return TestClient(create_app())


def _anpr_body(pilot, *, event_id: str, plate: str) -> dict:
    from access_control.tests.conftest import utcnow

    return {
        "controller_uid": pilot.controller_uid,
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


# ----------------------------- M3: no plate in logs -----------------------------


def test_plate_number_not_in_logs(pg_db, pilot, caplog) -> None:
    """M3: даже на DEBUG полный номер не должен попасть в application logs (§11)."""
    from access_control.tests.conftest import SigningClient, seed_permanent_vehicle

    plate = "01A001AA"
    seed_permanent_vehicle(pg_db, pilot, normalized=plate)
    client = SigningClient(_raw(), pilot.controller_uid)
    with caplog.at_level(logging.DEBUG, logger="access_control.services.ingestion"):
        resp = client.post(
            "/api/v1/access/camera-events/anpr",
            json=_anpr_body(pilot, event_id="m3-1", plate=plate),
        )
    assert resp.status_code == 200
    # §11 проверяет логи ПРИЛОЖЕНИЯ access_control. Глобальный caplog.text также
    # ловит SQL-echo SQLAlchemy (sqlalchemy.engine.Engine, INFO), где номер
    # неизбежно присутствует в параметрах INSERT — это инфраструктурный echo,
    # гейтится settings.DEBUG (выключен в прод), а не лог приложения. Фильтруем
    # записи по логгерам access_control.* — так тест проверяет реальный инвариант
    # и детерминирован независимо от версии pytest (порог захвата echo разнится).
    app_log_text = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name.startswith("access_control")
    )
    assert plate not in app_log_text


# ----------------------------- M4: generic 401 -----------------------------


def test_unknown_controller_generic_unauthorized(pg_db, pilot) -> None:
    """M4: неизвестный контроллер → 401 «unauthorized» (без раскрытия причины)."""
    from access_control.tests.conftest import SigningClient

    # Подпишем как несуществующий контроллер (валидная структура, неизвестный uid).
    client = SigningClient(_raw(), "ctrl-does-not-exist")
    resp = client.get("/api/v1/access/edge/ctrl-does-not-exist/access-snapshot")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "unauthorized"


def test_wrong_api_key_generic_unauthorized(pg_db, pilot) -> None:
    """M4: неверный api_key → тот же обобщённый 401 «unauthorized» (нет enumeration)."""
    from access_control.tests.conftest import SigningClient

    client = SigningClient(_raw(), pilot.controller_uid, api_key="totally-wrong-key")
    resp = client.get(f"/api/v1/access/edge/{pilot.controller_uid}/access-snapshot")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "unauthorized"


# ----------------------------- M5: trusted proxy XFF -----------------------------


def test_trusted_proxy_xff_foreign_ip_403(pg_db, pilot, monkeypatch) -> None:
    """M5: за доверенным прокси чужой X-Forwarded-For → 403 (берём IP из XFF, не прокси)."""
    from access_control.tests.conftest import SigningClient

    # allowlist разрешает только 9.9.9.9.
    pg_db.execute(
        text("UPDATE edge_controllers SET ip_allowlist = :al WHERE id = :i"),
        {"al": '["9.9.9.9"]', "i": pilot.controller_id},
    )
    pg_db.commit()
    # TestClient присылает request.client.host == 'testclient' — объявим его доверенным.
    monkeypatch.setenv("ACCESS_TRUSTED_PROXIES", "testclient")
    client = SigningClient(_raw(), pilot.controller_uid)
    resp = client.get(
        f"/api/v1/access/edge/{pilot.controller_uid}/access-snapshot",
        headers={"x-forwarded-for": "1.2.3.4"},  # чужой реальный IP
    )
    assert resp.status_code == 403


def test_trusted_proxy_xff_allowed_ip_passes(pg_db, pilot, monkeypatch) -> None:
    """M5: за доверенным прокси разрешённый X-Forwarded-For проходит."""
    from access_control.tests.conftest import SigningClient

    pg_db.execute(
        text("UPDATE edge_controllers SET ip_allowlist = :al WHERE id = :i"),
        {"al": '["9.9.9.9"]', "i": pilot.controller_id},
    )
    pg_db.commit()
    monkeypatch.setenv("ACCESS_TRUSTED_PROXIES", "testclient")
    client = SigningClient(_raw(), pilot.controller_uid)
    resp = client.get(
        f"/api/v1/access/edge/{pilot.controller_uid}/access-snapshot",
        headers={"x-forwarded-for": "9.9.9.9"},  # разрешённый реальный IP
    )
    assert resp.status_code == 200
