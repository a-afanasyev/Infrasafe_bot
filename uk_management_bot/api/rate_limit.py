"""Canonical slowapi limiter for the UK Management API.

Behind the shared nginx proxy on infrasafe.uz the limiter must:
  * key on the real client IP (see ``client_ip_key``), not the proxy IP;
  * share counters across uvicorn workers — in-memory storage gives each
    worker its own counter, so the effective limit is ~Nx and racy.

When ``USE_REDIS_RATE_LIMIT`` is set, counters live in Redis so all workers
share them. Prod runs ``--workers 2`` and sets the flag true; dev defaults
to in-memory.
"""
import logging

from fastapi import HTTPException
from slowapi import Limiter

from uk_management_bot.api.rate_limit_keys import client_ip_key
from uk_management_bot.config.settings import settings

logger = logging.getLogger(__name__)


def build_limiter() -> Limiter:
    """Construct the API limiter. A factory (not an inline expression) so
    tests can rebuild it with monkeypatched settings."""
    if settings.USE_REDIS_RATE_LIMIT and settings.REDIS_URL:
        logger.info("Rate limiter: redis storage (%s)", settings.REDIS_URL.split("@")[-1])
        return Limiter(
            key_func=client_ip_key,
            storage_uri=settings.REDIS_URL,
            strategy="fixed-window",
            # Redis unreachable → limits transparently falls back to an
            # in-process counter instead of erroring on every request.
            in_memory_fallback_enabled=True,
            # Deliberate fail-open: if even the fallback storage raises,
            # slowapi logs and ALLOWS the request rather than returning 500.
            # Acceptable here — auth endpoints still validate credentials,
            # and a brief unbounded window beats a hard outage.
            swallow_errors=True,
        )
    logger.info("Rate limiter: in-memory storage (USE_REDIS_RATE_LIMIT off)")
    return Limiter(key_func=client_ip_key)


async def rate_limit_backend_status() -> dict:
    """Probe the limiter's storage backend for observability (SEC-062).

    The limiter is intentionally fail-open: when Redis is unreachable it
    silently degrades to a per-worker in-memory counter (``in_memory_fallback``)
    so a Redis blip never returns 500 on auth endpoints. The hazard is that the
    degradation is *silent* — the effective limit balloons ~Nx (one counter per
    uvicorn worker) with no signal, which can mask both an outage and an abuse
    window. This probe surfaces the condition so it can be alerted on
    (startup ERROR log + ``/api/health/ratelimit``) rather than fail-open AND
    fail-quiet.

    Never raises — a probe that throws would defeat the fail-open contract.
    Returns ``redis_reachable=None`` when Redis isn't the configured backend.
    """
    if not (settings.USE_REDIS_RATE_LIMIT and settings.REDIS_URL):
        return {"configured_backend": "memory", "redis_reachable": None}
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(
            settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2
        )
        try:
            await client.ping()
        finally:
            await client.aclose()
        return {"configured_backend": "redis", "redis_reachable": True}
    except Exception as e:  # noqa: BLE001 — probe must never propagate
        logger.warning("rate-limit Redis backend unreachable: %s", e)
        return {"configured_backend": "redis", "redis_reachable": False}


limiter = build_limiter()


def auth_ratelimit_guard() -> None:
    """SEC-04 fail-closed gate for auth routes.

    When Redis is the configured rate-limit backend but unreachable, slowapi
    silently degrades to per-worker in-memory counters (~Nx effective limit at
    ``--workers N``) — a brute-force amplification window. SEC-062 detects and
    alerts; this MITIGATES by failing CLOSED on auth endpoints: while the
    backend is down, reject with 503 instead of allowing the amplified window.
    Non-auth routes keep the deliberate fail-open posture (availability over
    strictness) via slowapi's in-memory fallback.

    Reads slowapi's own cached ``_storage_dead`` flag (set on an observed
    storage failure, auto-reset on backend recovery) — no extra Redis round
    trip per request. ``getattr`` with a False default keeps this a safe no-op
    if a slowapi upgrade ever renames the attribute (degrades to fail-open,
    never crashes). A no-op when Redis isn't the configured backend (dev
    in-memory), so local development is unaffected.
    """
    if settings.USE_REDIS_RATE_LIMIT and getattr(limiter, "_storage_dead", False):
        raise HTTPException(
            status_code=503,
            detail="Authentication temporarily unavailable (rate-limit backend degraded). Retry shortly.",
        )
