"""SEC-064 — optional bearer-token gate on operational health endpoints.

`/api/health/outbox` and `/api/health/ratelimit` expose internal state (outbox
lag, Redis reachability). They're gated by `require_health_token`, which is a
no-op when `HEALTH_METRICS_TOKEN` is unset (dev / before ops opts in) and
enforces `Authorization: Bearer <token>` once set. Liveness probes (/health,
/api/health) stay open regardless.
"""
import pytest

from uk_management_bot.config.settings import settings


@pytest.mark.asyncio
async def test_health_endpoints_open_when_token_unset(client, monkeypatch):
    monkeypatch.setattr(settings, "HEALTH_METRICS_TOKEN", "")
    assert (await client.get("/api/health/outbox")).status_code == 200
    assert (await client.get("/api/health/ratelimit")).status_code == 200


@pytest.mark.asyncio
async def test_outbox_requires_token_when_set(client, monkeypatch):
    monkeypatch.setattr(settings, "HEALTH_METRICS_TOKEN", "s3cret-token")

    # No header → 401.
    assert (await client.get("/api/health/outbox")).status_code == 401
    # Wrong token → 401.
    r = await client.get("/api/health/outbox", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
    # Correct token → 200.
    r = await client.get(
        "/api/health/outbox", headers={"Authorization": "Bearer s3cret-token"}
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_ratelimit_health_gated_too(client, monkeypatch):
    monkeypatch.setattr(settings, "HEALTH_METRICS_TOKEN", "s3cret-token")
    assert (await client.get("/api/health/ratelimit")).status_code == 401
    r = await client.get(
        "/api/health/ratelimit", headers={"Authorization": "Bearer s3cret-token"}
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_liveness_probes_stay_open_when_token_set(client, monkeypatch):
    monkeypatch.setattr(settings, "HEALTH_METRICS_TOKEN", "s3cret-token")
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/api/health")).status_code == 200
