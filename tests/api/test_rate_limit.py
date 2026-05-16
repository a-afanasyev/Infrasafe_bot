"""Tests for rate-limiting infrastructure.

Covers the real-client-IP key function, Redis-mode limiter construction, an
end-to-end 429 with per-IP bucket isolation, and the public-board TTL cache.
The 429 test uses a throwaway Limiter on a throwaway app so it never touches
the process-global production limiter state.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.datastructures import Headers

from uk_management_bot.api.rate_limit_keys import client_ip_key
from uk_management_bot.api import rate_limit as rate_limit_module
from uk_management_bot.database.models.request import Request as RequestModel


# ── client_ip_key — unit ─────────────────────────────────────────────

class _StubRequest:
    """Minimal stand-in for starlette Request: headers + .client.host."""
    def __init__(self, headers: dict[str, str], client_host: str | None = "10.0.0.1"):
        self.headers = Headers(headers)
        self.client = type("C", (), {"host": client_host})() if client_host else None


def test_client_ip_key_honors_x_real_ip():
    assert client_ip_key(_StubRequest({"X-Real-IP": "9.9.9.9"})) == "9.9.9.9"


def test_client_ip_key_header_is_case_insensitive():
    assert client_ip_key(_StubRequest({"x-real-ip": "8.8.8.8"})) == "8.8.8.8"


def test_client_ip_key_falls_back_to_remote_address():
    # No X-Real-IP → slowapi get_remote_address → request.client.host
    assert client_ip_key(_StubRequest({}, client_host="127.0.0.1")) == "127.0.0.1"


def test_client_ip_key_ignores_blank_header():
    assert client_ip_key(_StubRequest({"X-Real-IP": "   "}, client_host="127.0.0.1")) == "127.0.0.1"


def test_client_ip_key_distinct_ips_distinct_keys():
    a = client_ip_key(_StubRequest({"X-Real-IP": "1.1.1.1"}))
    b = client_ip_key(_StubRequest({"X-Real-IP": "2.2.2.2"}))
    assert a != b


# ── build_limiter — construction in both modes ───────────────────────

def test_build_limiter_redis_mode_constructs(monkeypatch):
    """Redis mode must construct without raising. `limits` connects lazily,
    so no live Redis is needed — this guards against Limiter(...) kwarg typos
    / params unsupported by the pinned slowapi."""
    monkeypatch.setattr(rate_limit_module.settings, "USE_REDIS_RATE_LIMIT", True)
    monkeypatch.setattr(rate_limit_module.settings, "REDIS_URL", "redis://localhost:6379/0")
    limiter = rate_limit_module.build_limiter()
    assert isinstance(limiter, Limiter)


def test_build_limiter_memory_mode_constructs(monkeypatch):
    monkeypatch.setattr(rate_limit_module.settings, "USE_REDIS_RATE_LIMIT", False)
    limiter = rate_limit_module.build_limiter()
    assert isinstance(limiter, Limiter)


# ── End-to-end 429 with isolated limiter ─────────────────────────────

@pytest.mark.asyncio
async def test_rate_limit_429_and_per_ip_isolation():
    """Throwaway app + dedicated Limiter at 2/minute. Same X-Real-IP: third
    call 429s. Different X-Real-IP: own bucket, still 200 — proving the proxy
    no longer collapses every client into one bucket."""
    test_limiter = Limiter(key_func=client_ip_key)
    app = FastAPI()
    app.state.limiter = test_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.get("/ping")
    @test_limiter.limit("2/minute")
    async def ping(request: Request):
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ip_a = {"X-Real-IP": "1.1.1.1"}
        r1 = await ac.get("/ping", headers=ip_a)
        r2 = await ac.get("/ping", headers=ip_a)
        r3 = await ac.get("/ping", headers=ip_a)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 429

        # Different IP → independent bucket.
        r_other = await ac.get("/ping", headers={"X-Real-IP": "2.2.2.2"})
        assert r_other.status_code == 200


# ── Public board TTL cache ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_public_board_cache_serves_stale_within_ttl(client, db_session, manager_user):
    """A row inserted after the first call is NOT reflected in the second call
    within the TTL window — proving the second call is served from cache, not
    re-queried. (The autouse fixture resets the cache between tests.)"""
    first = await client.get("/api/v2/public/board")
    assert first.status_code == 200
    assert first.json()["status_counts"]["Новая"] == 0

    db_session.add(RequestModel(
        request_number="260516-900", user_id=manager_user.id,
        category="Электрика", description="x", status="Новая",
    ))
    await db_session.commit()

    second = await client.get("/api/v2/public/board")
    assert second.status_code == 200
    # Still the cached payload — the new "Новая" request is not visible yet.
    assert second.json()["status_counts"]["Новая"] == 0
    assert second.json() == first.json()
