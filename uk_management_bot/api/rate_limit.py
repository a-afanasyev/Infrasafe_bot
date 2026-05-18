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


limiter = build_limiter()
