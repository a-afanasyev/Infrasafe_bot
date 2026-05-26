"""SEC-019 — rate-limit guard on POST /api/v2/auth/set-password.

Pre-fix the endpoint accepted unlimited POSTs from an authenticated session;
a stolen access token could be replayed in a tight loop to brute-force
confirm_password drift, churn bcrypt hash slots, or flood DB writes. We cap
at 5/minute per real client IP — same shape as the rest of /auth/*.

The slowapi limiter is module-level (process-global, in-memory in tests).
We do NOT call `limiter.reset()` — it clears storage for the whole test
process, which breaks neighbour tests' per-IP buckets. Instead we use
TEST-NET-3 IPs that no other test touches, so our buckets stay isolated
regardless of suite order.
"""
import pytest


VALID_BODY = {"password": "GoodPassword123", "confirm_password": "GoodPassword123"}


@pytest.mark.asyncio
async def test_set_password_rate_limited_at_5_per_minute(client):
    """Six rapid POSTs from one IP: calls 1–5 succeed, 6th returns 429."""
    headers = {"X-Real-IP": "203.0.113.31"}  # TEST-NET-3 (RFC 5737)

    for i in range(5):
        r = await client.post("/api/v2/auth/set-password", json=VALID_BODY, headers=headers)
        assert r.status_code == 200, f"call {i+1} expected 200, got {r.status_code}: {r.text}"

    r = await client.post("/api/v2/auth/set-password", json=VALID_BODY, headers=headers)
    assert r.status_code == 429, r.text


@pytest.mark.asyncio
async def test_set_password_per_ip_isolation(client):
    """A different real client IP gets its own bucket — limit is per-IP,
    not global. Uses different octets from the burst test so the buckets
    don't collide across tests in one pytest process."""
    ip_a = {"X-Real-IP": "203.0.113.33"}
    ip_b = {"X-Real-IP": "203.0.113.34"}

    for _ in range(5):
        await client.post("/api/v2/auth/set-password", json=VALID_BODY, headers=ip_a)

    # ip_a exhausted; ip_b still has its full quota.
    r = await client.post("/api/v2/auth/set-password", json=VALID_BODY, headers=ip_b)
    assert r.status_code == 200, r.text
