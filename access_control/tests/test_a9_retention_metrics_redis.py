"""A9-P2-16 / A9-P3-2 / A9-P3-23: ретеншн медиа, токен /metrics, Redis/локи/IP.

* P2-16: 30-дневный ретеншн обнулял только ``*_photo_url`` — сам файл оставался в
  медиа-сервисе (канал + ``media_files``) и отдавался по id. Теперь порядок
  «сначала DELETE /media/{id}, потом ссылка»; временный сбой оставляет ссылку до
  следующего тика; пачка ограничена; общий с другим событием id не удаляется.
* P3-2: ``/metrics`` access-api без токена. Гейт ``ACCESS_METRICS_TOKEN``: не задан
  — открыт (совместимость со скрейпом alloy), задан — ``Bearer`` обязателен.
* P3-23: sync Redis без таймаутов, пул на каждый WS не закрывался; advisory-ключи
  barrier/gate/controller в одном пространстве; 6 копий ``_client_ip`` мимо
  ``resolve_client_ip``.
"""
from __future__ import annotations

import asyncio
import datetime as dt
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from access_control.app.main import create_app
from access_control.integrations import media as media_mod
from access_control.integrations.media import AccessMediaClient
from access_control.services import code_rate_limit, device_auth, redis_timeouts
from access_control.services import event_broadcaster as eb
from access_control.services import metrics as metrics_mod
from access_control.services import locks
from access_control.services import photo_retention as pr
from access_control.services import retention_worker as rw
from access_control.tests.conftest import SigningClient, seed_user, utcnow
from access_control.tests.test_access_media import FakeMediaClient
from access_control.tests.test_operator_api_rbac import _fake_user
from access_control.tests.test_operator_read_api import _seed_camera_event
from uk_management_bot.api.dependencies import get_current_user

ACCESS_ROOT = Path(__file__).resolve().parents[1]


# ------------------------------ A9-P2-16: ретеншн медиа ------------------------------


def _status_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("DELETE", "http://media/api/v1/media/1")
    return httpx.HTTPStatusError(
        f"media {code}", request=req, response=httpx.Response(code, request=req)
    )


class _ScriptedMedia:
    """Фейк медиа-сервиса: поведение DELETE/GET по media_id.

    ok — удалён (200); gone404 — 404, GET 404; compensated — 404, но GET active
    (Telegram-удаление упало, сага вернула active); locked — 409 + active
    (publication-lock); was_deleted — 409 + deleted; transient — 503.
    """

    def __init__(self, script: dict[int, str] | None = None) -> None:
        self.script = dict(script or {})
        self.calls: list[int] = []
        self.deleted: list[int] = []

    async def delete_file(self, media_id) -> bool:
        media_id = int(media_id)
        self.calls.append(media_id)
        mode = self.script.get(media_id, "ok")
        if mode == "ok":
            self.deleted.append(media_id)
            return True
        if mode in ("gone404", "compensated"):
            return False
        if mode in ("locked", "was_deleted"):
            raise _status_error(409)
        raise _status_error(503)

    async def get_status(self, media_id) -> str | None:
        return {
            "gone404": None,
            "compensated": "active",
            "locked": "active",
            "was_deleted": "deleted",
        }.get(self.script.get(int(media_id), "ok"))


def _refs(db, event_id: str):
    db.commit()  # свежий снимок после записей сессий тика
    return tuple(
        db.execute(
            text(
                "SELECT plate_photo_url, overview_photo_url FROM camera_events "
                "WHERE event_id = :e"
            ),
            {"e": event_id},
        ).first()
    )


def _old(pg_db, pilot, event_id: str, plate=None, overview=None, days: int = 31) -> int:
    pk = _seed_camera_event(
        pg_db, pilot, event_id=event_id, plate="01OLD00",
        captured_at=utcnow() - dt.timedelta(days=days),
        plate_photo_url=plate, overview_photo_url=overview,
    )
    pg_db.commit()
    return pk


def _run(sessionmaker, media, **kw) -> int:
    return pr.run_photo_retention(sessionmaker, client=media, now=utcnow(), **kw)


def test_file_deleted_before_ref_cleared(pg_db, pilot, _pg_sessionmaker) -> None:
    _old(pg_db, pilot, "ev-ok", plate="media://900", overview="media://901")
    media = _ScriptedMedia()
    assert _run(_pg_sessionmaker, media) == 1
    assert sorted(media.deleted) == [900, 901]
    assert _refs(pg_db, "ev-ok") == (None, None)


def test_transient_failure_keeps_ref_and_next_tick_retries(
    pg_db, pilot, _pg_sessionmaker
) -> None:
    _old(pg_db, pilot, "ev-tr", plate="media://910", overview="media://911")
    media = _ScriptedMedia({911: "transient"})
    _run(_pg_sessionmaker, media)
    # plate удалён → обнулён; overview — сбой → ссылка (и media_id) сохранены.
    assert _refs(pg_db, "ev-tr") == (None, "media://911")

    media.script[911] = "ok"
    assert _run(_pg_sessionmaker, media) == 1
    assert media.deleted == [910, 911]
    assert _refs(pg_db, "ev-tr") == (None, None)


@pytest.mark.parametrize("mode", ["gone404", "was_deleted", "locked"])
def test_clearable_outcomes_null_ref(pg_db, pilot, _pg_sessionmaker, mode) -> None:
    """404 / уже удалён / удерживается публикацией → ссылку события обнуляем."""
    _old(pg_db, pilot, "ev-cl", plate="media://920")
    _run(_pg_sessionmaker, _ScriptedMedia({920: mode}))
    assert _refs(pg_db, "ev-cl") == (None, None)


def test_compensated_telegram_failure_keeps_ref(pg_db, pilot, _pg_sessionmaker) -> None:
    """404 от media, но файл снова active (сага откатилась) — это не «удалён»."""
    _old(pg_db, pilot, "ev-cmp", plate="media://925")
    _run(_pg_sessionmaker, _ScriptedMedia({925: "compensated"}))
    assert _refs(pg_db, "ev-cmp") == ("media://925", None)


def test_batch_limit(pg_db, pilot, _pg_sessionmaker) -> None:
    for i in range(3):
        _old(pg_db, pilot, f"ev-b{i}", plate=f"media://{930 + i}")
    media = _ScriptedMedia()
    assert _run(_pg_sessionmaker, media, limit=2) == 2
    assert media.calls == [930, 931]
    assert _refs(pg_db, "ev-b2") == ("media://932", None)
    assert _run(_pg_sessionmaker, media, limit=2) == 1
    assert media.calls == [930, 931, 932]


def test_batch_limit_default_is_bounded() -> None:
    assert 0 < pr.PHOTO_RETENTION_BATCH <= 500


def test_shared_id_between_expired_events_deleted_once(
    pg_db, pilot, _pg_sessionmaker
) -> None:
    _old(pg_db, pilot, "ev-s1", plate="media://940")
    _old(pg_db, pilot, "ev-s2", overview="media://940", days=40)
    media = _ScriptedMedia()
    assert _run(_pg_sessionmaker, media) == 2
    assert media.calls == [940]
    assert _refs(pg_db, "ev-s1") == (None, None)
    assert _refs(pg_db, "ev-s2") == (None, None)


def test_id_shared_with_fresh_event_not_deleted(pg_db, pilot, _pg_sessionmaker) -> None:
    _old(pg_db, pilot, "ev-old", plate="media://950")
    _old(pg_db, pilot, "ev-fresh", overview="media://950", days=1)
    media = _ScriptedMedia()
    assert _run(_pg_sessionmaker, media) == 1
    assert media.calls == []
    assert _refs(pg_db, "ev-old") == (None, None)
    assert _refs(pg_db, "ev-fresh") == (None, "media://950")


def test_legacy_raw_url_cleared_without_media_calls(pg_db, pilot, _pg_sessionmaker) -> None:
    _old(pg_db, pilot, "ev-leg", plate="https://cdn.example/legacy.jpg")
    media = _ScriptedMedia()
    assert _run(_pg_sessionmaker, media) == 1
    assert media.calls == []
    assert _refs(pg_db, "ev-leg") == (None, None)


def test_photo_tick_uses_media_client(pg_db, pilot, monkeypatch) -> None:
    monkeypatch.setattr(rw, "_photo_state", None)
    _old(pg_db, pilot, "ev-tick", plate="media://960")
    fake = FakeMediaClient()
    media_mod.reset_access_media_client(fake)
    try:
        assert rw._photo_tick() == 1
        assert rw._photo_tick() == 0
    finally:
        media_mod.reset_access_media_client(None)
    assert fake.deleted == [960]


async def test_retire_network_error_is_transient() -> None:
    class _Down(FakeMediaClient):
        async def delete_file(self, media_id):
            raise httpx.ConnectError("down", request=httpx.Request("DELETE", "http://m"))

    outcome = await media_mod.retire_media_file(_Down(), 1)
    assert outcome is media_mod.MediaRetireOutcome.TRANSIENT


async def test_delete_media_best_effort_continues_after_failure() -> None:
    class _Flaky(FakeMediaClient):
        async def delete_file(self, media_id) -> bool:
            if int(media_id) == 1:
                raise httpx.ConnectError("down", request=httpx.Request("DELETE", "http://m"))
            return await super().delete_file(media_id)

    fake = _Flaky()
    assert await media_mod.delete_media_best_effort(fake, (1, 2)) == 1
    assert fake.deleted == [2]


def _mock_client(handler) -> AccessMediaClient:
    client = AccessMediaClient(base_url="http://media", api_key="k")
    client._client = lambda: httpx.AsyncClient(  # type: ignore[method-assign]
        base_url="http://media/api/v1", transport=httpx.MockTransport(handler)
    )
    return client


@pytest.mark.parametrize(("code", "expected"), [(200, True), (404, False)])
async def test_media_client_delete_file(code: int, expected: bool) -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(code, json={})

    assert await _mock_client(handler).delete_file(42) is expected
    assert seen == [("DELETE", "/api/v1/media/42")]


async def test_media_client_delete_file_raises_on_conflict() -> None:
    client = _mock_client(lambda request: httpx.Response(409, json={}))
    with pytest.raises(httpx.HTTPStatusError):
        await client.delete_file(42)


@pytest.mark.parametrize(("code", "body", "expected"), [
    (200, {"status": "deleted"}, "deleted"),
    (404, {}, None),
])
async def test_media_client_get_status(code, body, expected) -> None:
    client = _mock_client(lambda request: httpx.Response(code, json=body))
    assert await client.get_status(42) == expected


def test_retention_docstring_has_no_phantom_object_storage() -> None:
    assert "MinIO" not in (pr.__doc__ or "")
    assert "S3" not in (pr.__doc__ or "")


# ------------------------------ A9-P3-2: /metrics token ------------------------------


def test_metrics_open_when_token_unset(pg_db, pilot, monkeypatch) -> None:
    monkeypatch.delenv("ACCESS_METRICS_TOKEN", raising=False)
    assert TestClient(create_app()).get("/metrics").status_code == 200


@pytest.mark.parametrize("auth", [None, "Bearer wrong", "sekret-token"])
def test_metrics_rejects_without_valid_bearer(pg_db, pilot, monkeypatch, auth) -> None:
    monkeypatch.setenv("ACCESS_METRICS_TOKEN", "sekret-token")
    headers = {"Authorization": auth} if auth else {}
    resp = TestClient(create_app()).get("/metrics", headers=headers)
    assert resp.status_code == 401


def test_metrics_allows_valid_bearer(pg_db, pilot, monkeypatch) -> None:
    monkeypatch.setenv("ACCESS_METRICS_TOKEN", "sekret-token")
    resp = TestClient(create_app()).get(
        "/metrics", headers={"Authorization": "Bearer sekret-token"}
    )
    assert resp.status_code == 200


# ------------------------------ A9-P3-23: Redis ------------------------------


def test_redis_broker_sync_client_has_timeouts() -> None:
    broker = eb.RedisBroker("redis://127.0.0.1:1/0")
    kwargs = broker._sync_client.connection_pool.connection_kwargs
    assert kwargs["socket_timeout"] == eb.REDIS_SOCKET_TIMEOUT_SECONDS
    assert kwargs["socket_connect_timeout"] == eb.REDIS_CONNECT_TIMEOUT_SECONDS


class _FakePubSub:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class _FakeAsyncRedis:
    def __init__(self) -> None:
        self.pubsub_obj = _FakePubSub()
        self.closed = False

    def pubsub(self) -> _FakePubSub:
        return self.pubsub_obj

    async def aclose(self) -> None:
        self.closed = True


async def test_redis_subscription_close_releases_client_pool(monkeypatch) -> None:
    import redis.asyncio as aioredis

    created: list[tuple[_FakeAsyncRedis, dict]] = []

    def _from_url(url, **kwargs):
        client = _FakeAsyncRedis()
        created.append((client, kwargs))
        return client

    monkeypatch.setattr(aioredis, "from_url", _from_url)
    sub = eb.RedisBroker("redis://127.0.0.1:1/0").subscribe()
    sub.close()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    client, kwargs = created[0]
    assert client.pubsub_obj.closed and client.closed
    assert kwargs["socket_connect_timeout"] == eb.REDIS_CONNECT_TIMEOUT_SECONDS


# ------------------------------ A9-P3-23: advisory-ключи ------------------------------


def test_lock_keys_live_in_separate_namespaces() -> None:
    barrier = locks.canonical_lock_key(7, 7, 7)
    gate = locks.canonical_lock_key(None, 7, 7)
    controller = locks.canonical_lock_key(None, None, 7)
    assert len({barrier, gate, controller}) == 3
    assert barrier == (locks.LOCK_NS_BARRIER, 7)
    assert gate == (locks.LOCK_NS_GATE, 7)
    assert controller == (locks.LOCK_NS_CONTROLLER, 7)
    assert locks.canonical_lock_key(None, None, None) is None


def test_barrier_lock_is_two_key_and_does_not_block_same_gate_id(
    pg_db, _pg_sessionmaker
) -> None:
    locks.barrier_advisory_lock(pg_db, 5)
    row = pg_db.execute(
        text(
            "SELECT classid, objid, objsubid FROM pg_locks "
            "WHERE locktype = 'advisory' AND pid = pg_backend_pid()"
        )
    ).first()
    assert tuple(row) == (locks.LOCK_NS_BARRIER, 5, 2)  # objsubid=2 — (int4, int4)
    other = _pg_sessionmaker()
    try:
        got = other.execute(
            text("SELECT pg_try_advisory_xact_lock(:ns, 5)"),
            {"ns": locks.LOCK_NS_GATE},
        ).scalar()
        assert got is True  # gate 5 ≠ barrier 5
    finally:
        other.rollback()
        other.close()
    pg_db.rollback()


# ------------------------------ A9-P3-23: один _client_ip ------------------------------


def test_no_local_client_ip_copies_in_api() -> None:
    offenders = [
        p.name
        for p in (ACCESS_ROOT / "api").glob("*.py")
        if "def _client_ip(" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_audit_ip_honours_trusted_proxy(pg_db, pilot, monkeypatch) -> None:
    monkeypatch.setenv("ACCESS_TRUSTED_PROXIES", "testclient")
    uid = seed_user(pg_db, roles="security_operator")
    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_user(uid, "security_operator")
    resp = TestClient(app).post(
        f"/api/v1/access/barriers/{pilot.barrier_id}/manual-open",
        json={"reason": "проверка", "source": "tech_check"},
        headers={"X-Forwarded-For": "203.0.113.7, 10.0.0.1"},
    )
    assert resp.status_code == 200, resp.text
    pg_db.commit()
    ip = pg_db.execute(
        text(
            "SELECT ip_address FROM access_audit_logs "
            "WHERE action = 'access.barrier_manual_open' ORDER BY id DESC LIMIT 1"
        )
    ).scalar()
    assert str(ip) == "203.0.113.7"


# ---------------- ревью A9-P2-16: курсор пачки и «застревание» ----------------


def test_cursor_rotates_past_permanently_stuck_events(
    pg_db, pilot, _pg_sessionmaker
) -> None:
    """Постоянно-транзитные события не занимают пачку навсегда."""
    for i in range(3):
        _old(pg_db, pilot, f"ev-r{i}", plate=f"media://{970 + i}")
    media = _ScriptedMedia({970: "transient", 971: "transient"})
    kw = {"client": media, "now": utcnow(), "limit": 2}

    cleared, state = pr.advance_photo_retention(
        _pg_sessionmaker, pr.RetentionState(), **kw
    )
    assert cleared == 0 and media.calls == [970, 971]
    cleared, state = pr.advance_photo_retention(_pg_sessionmaker, state, **kw)
    # Второй тик начинает после курсора: 972 удалён, затем по кругу — 970.
    assert cleared == 1
    assert media.calls[2:] == [970, 972]
    assert _refs(pg_db, "ev-r2") == (None, None)


def test_stuck_ticks_warn_and_reset(pg_db, pilot, _pg_sessionmaker, caplog) -> None:
    _old(pg_db, pilot, "ev-stuck", plate="media://980")
    media = _ScriptedMedia({980: "transient"})
    kw = {"client": media, "now": utcnow()}
    state = pr.RetentionState()
    with caplog.at_level("WARNING", logger=pr.__name__):
        for _ in range(pr.STUCK_WARN_TICKS):
            _, state = pr.advance_photo_retention(_pg_sessionmaker, state, **kw)
    assert state.stuck_ticks == pr.STUCK_WARN_TICKS
    assert any("тиков подряд" in r.getMessage() for r in caplog.records)
    assert b"access_photo_retention_stuck_ticks 3.0" in metrics_mod.prometheus_text()

    media.script[980] = "ok"
    _, state = pr.advance_photo_retention(_pg_sessionmaker, state, **kw)
    assert state.stuck_ticks == 0
    assert b"access_photo_retention_stuck_ticks 0.0" in metrics_mod.prometheus_text()


# ---------------- ревью A9-P3-23: таймауты sync Redis device-auth/кодов ----------------


def test_nonce_store_redis_client_has_timeouts(monkeypatch) -> None:
    monkeypatch.setenv("ACCESS_NONCE_BACKEND", "redis")
    device_auth.reset_nonce_store(None)
    try:
        store = device_auth.get_nonce_store()
        kwargs = store._client.connection_pool.connection_kwargs
    finally:
        device_auth.reset_nonce_store(None)
    assert kwargs["socket_timeout"] == redis_timeouts.REDIS_SOCKET_TIMEOUT_SECONDS
    assert kwargs["socket_connect_timeout"] == redis_timeouts.REDIS_CONNECT_TIMEOUT_SECONDS


def test_code_rate_limit_redis_client_has_timeouts(monkeypatch) -> None:
    monkeypatch.setenv("ACCESS_NONCE_BACKEND", "redis")
    code_rate_limit.reset_failure_store(None)
    try:
        store = code_rate_limit.get_failure_store()
        kwargs = store._client.connection_pool.connection_kwargs
    finally:
        code_rate_limit.reset_failure_store(None)
    assert kwargs["socket_timeout"] == redis_timeouts.REDIS_SOCKET_TIMEOUT_SECONDS
    assert kwargs["socket_connect_timeout"] == redis_timeouts.REDIS_CONNECT_TIMEOUT_SECONDS


class _PausedRedis:
    def set(self, **kwargs):
        import redis

        raise redis.TimeoutError("Timeout reading from socket")


def test_redis_pause_gives_fast_fail_closed_503(pg_db, pilot) -> None:
    """Redis на паузе → device-auth отвечает 503 (fail-closed), а не 500/зависание."""
    device_auth.reset_nonce_store(device_auth.RedisNonceStore(_PausedRedis()))
    try:
        client = SigningClient(TestClient(create_app()), pilot.controller_uid)
        resp = client.post(
            f"/api/v1/access/edge/{pilot.controller_uid}/heartbeat",
            json={"clock_offset_ms": 0},
        )
    finally:
        device_auth.reset_nonce_store(None)
    assert resp.status_code == 503
