"""SEC-062 — rate-limiter backend observability.

The API limiter is deliberately fail-open (``in_memory_fallback_enabled`` +
``swallow_errors``) so a Redis blip never 500s auth endpoints. The danger is
*silent* degradation: when Redis is unreachable each uvicorn worker falls back
to its own in-memory counter, so the effective limit balloons ~Nx with no
signal. ``rate_limit_backend_status()`` makes that condition observable (startup
ERROR log + ``/api/health/ratelimit``) so ops can alert instead of finding out
via abuse.

These tests pin the helper's three states: redis-configured-and-up,
redis-configured-and-down (must log + report False, never raise), and
in-memory mode (not configured).
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from uk_management_bot.api import rate_limit
from uk_management_bot.config.settings import settings


def _fake_from_url_factory(ping_result=None, ping_exc=None):
    """Build a stand-in ``redis.asyncio.from_url`` returning a client whose
    async ``ping``/``aclose`` are controllable."""
    def _from_url(*args, **kwargs):
        client = AsyncMock()
        if ping_exc is not None:
            client.ping.side_effect = ping_exc
        else:
            client.ping.return_value = ping_result
        return client
    return _from_url


async def test_backend_status_memory_mode(monkeypatch):
    """USE_REDIS_RATE_LIMIT off → memory backend, reachable is None (n/a)."""
    monkeypatch.setattr(settings, "USE_REDIS_RATE_LIMIT", False)
    status = await rate_limit.rate_limit_backend_status()
    assert status == {"configured_backend": "memory", "redis_reachable": None}


async def test_backend_status_redis_up(monkeypatch):
    """Redis configured and ping succeeds → redis backend, reachable True."""
    monkeypatch.setattr(settings, "USE_REDIS_RATE_LIMIT", True)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    import redis.asyncio as aioredis
    monkeypatch.setattr(aioredis, "from_url", _fake_from_url_factory(ping_result=True))

    status = await rate_limit.rate_limit_backend_status()
    assert status == {"configured_backend": "redis", "redis_reachable": True}


async def test_backend_status_redis_down_logs_and_reports_false(monkeypatch, caplog):
    """Redis configured but ping raises → reachable False, WARNING logged,
    NEVER raises (fail-open invariant must hold for the probe too)."""
    monkeypatch.setattr(settings, "USE_REDIS_RATE_LIMIT", True)
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    import redis.asyncio as aioredis
    monkeypatch.setattr(
        aioredis, "from_url",
        _fake_from_url_factory(ping_exc=ConnectionError("connection refused")),
    )

    with caplog.at_level(logging.WARNING, logger=rate_limit.logger.name):
        status = await rate_limit.rate_limit_backend_status()

    assert status == {"configured_backend": "redis", "redis_reachable": False}
    assert any("unreachable" in r.message.lower() for r in caplog.records), (
        "expected a WARNING naming the unreachable Redis backend"
    )
