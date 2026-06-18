"""ARCH-012: health / metrics endpoints extracted from `api/main.py`.

Liveness probes (`/health`, `/api/health`) are intentionally open; the
state-exposing endpoints (`/api/health/ratelimit`, `/api/health/outbox`,
`/metrics`) are gated by ``require_health_token`` (SEC-064). Paths are absolute
and the router is included without a prefix, so the surface is unchanged.
"""
import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response

from uk_management_bot.api.rate_limit import rate_limit_backend_status
from uk_management_bot.config.settings import settings

_logger = logging.getLogger(__name__)

router = APIRouter()


def require_health_token(authorization: str | None = Header(default=None)):
    """SEC-064: gate operational health endpoints (/api/health/outbox,
    /api/health/ratelimit) which expose internal state (outbox lag, Redis
    reachability). No-op when ``HEALTH_METRICS_TOKEN`` is unset (dev / before
    ops opts in), so existing scrapers and the OPS-112 curl checks keep
    working. When the token is set, require ``Authorization: Bearer <token>``
    with a constant-time compare. Liveness probes (/health, /api/health) are
    intentionally left open."""
    token = settings.HEALTH_METRICS_TOKEN
    if not token:
        return
    expected = f"Bearer {token}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/health")
async def health():
    # Internal docker healthcheck — kept stable for Dockerfile.api HEALTHCHECK
    # and docker-compose probes (plan §4.6 variant A).
    return {"status": "healthy", "service": "api"}


@router.get("/api/health")
async def api_health():
    # Public health, exposed via nginx as /uk/api/health (plan §4.6).
    # Intentionally minimal: no service-name, no version — reduces fingerprinting.
    return {"ok": True}


@router.get("/api/health/ratelimit", dependencies=[Depends(require_health_token)])
async def ratelimit_health():
    # SEC-062: rate-limiter storage backend health for monitoring/alerting.
    # `redis_reachable: false` means the limiter has silently degraded to
    # per-worker in-memory counters — alert on it.
    return await rate_limit_backend_status()


async def _compute_outbox_metrics() -> dict:
    """Shared outbox lag metrics for `/api/health/outbox` (JSON) and `/metrics`
    (Prometheus). Never raises — returns an `error` key on failure."""
    from sqlalchemy import select, func
    from datetime import datetime, timedelta, timezone
    from uk_management_bot.database.models.webhook_outbox import WebhookOutbox

    if not settings.INFRASAFE_WEBHOOK_ENABLED:
        return {"enabled": False, "pending": 0, "oldest_pending_age_sec": 0, "failed_last_24h": 0, "stuck_in_flight": 0}

    from uk_management_bot.database.session import AsyncSessionLocal
    if AsyncSessionLocal is None:
        return {"enabled": True, "error": "db_unavailable"}

    now = datetime.now(timezone.utc)
    try:
        async with AsyncSessionLocal() as db:
            pending = await db.scalar(
                select(func.count(WebhookOutbox.id))
                .where(WebhookOutbox.status == "pending")
            ) or 0
            oldest = await db.scalar(
                select(func.min(WebhookOutbox.created_at))
                .where(WebhookOutbox.status == "pending")
            )
            failed_24h = await db.scalar(
                select(func.count(WebhookOutbox.id))
                .where(
                    WebhookOutbox.status == "failed",
                    WebhookOutbox.created_at > now - timedelta(hours=24),
                )
            ) or 0
            # PR-5: in_flight старше lease = владелец упал и запись ждёт
            # reclaim. Стабильно >0 — признак crash-loop'а воркера (алерт).
            lease_cutoff = now - timedelta(
                seconds=settings.INFRASAFE_OUTBOX_LEASE_SECONDS
            )
            stuck_in_flight = await db.scalar(
                select(func.count(WebhookOutbox.id))
                .where(
                    WebhookOutbox.status == "in_flight",
                    WebhookOutbox.claimed_at < lease_cutoff,
                )
            ) or 0
        # SQLite returns naive datetimes; Postgres returns tz-aware. Normalise
        # so the subtraction below never raises on a naive/aware mismatch.
        if oldest is not None and oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        return {
            "enabled": True,
            "pending": pending,
            "oldest_pending_age_sec": (now - oldest).total_seconds() if oldest else 0,
            "failed_last_24h": failed_24h,
            "stuck_in_flight": stuck_in_flight,
        }
    except Exception:
        _logger.exception("outbox metrics computation failed")
        return {"enabled": True, "error": "internal_error"}


@router.get("/api/health/outbox", dependencies=[Depends(require_health_token)])
async def outbox_health():
    """Outbox lag metrics for monitoring / alerting.

    Returns 200 always (so HTTP probes don't flap); the consumer (Prometheus
    scrape, alert rule) decides thresholds.
    """
    return await _compute_outbox_metrics()


@router.get("/metrics", dependencies=[Depends(require_health_token)])
async def prometheus_metrics():
    """OPS-105: Prometheus exposition of outbox lag gauges.

    Token-gated like the other health endpoints (SEC-064) — Prometheus scrapes
    with a bearer token. Gauges are recomputed per scrape from the same source
    as `/api/health/outbox`. When webhooks are disabled or DB is unavailable
    the gauges are simply absent (consumer treats missing as 0/unknown).
    """
    from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest

    metrics = await _compute_outbox_metrics()
    registry = CollectorRegistry()

    if metrics.get("enabled") and "error" not in metrics:
        Gauge("uk_outbox_pending", "Pending webhook_outbox records", registry=registry).set(
            metrics["pending"]
        )
        Gauge(
            "uk_outbox_oldest_pending_age_seconds",
            "Age of the oldest pending outbox record (seconds)",
            registry=registry,
        ).set(metrics["oldest_pending_age_sec"])
        Gauge(
            "uk_outbox_failed_last_24h",
            "Outbox records that ended in 'failed' in the last 24h",
            registry=registry,
        ).set(metrics["failed_last_24h"])
        Gauge(
            "uk_outbox_stuck_in_flight",
            "in_flight outbox records older than the claim lease (worker crash-loop signal)",
            registry=registry,
        ).set(metrics["stuck_in_flight"])

    return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
