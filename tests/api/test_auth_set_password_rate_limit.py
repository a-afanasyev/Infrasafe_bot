"""SEC-019 — rate-limit guard on POST /api/v2/auth/set-password.

Pre-fix the endpoint accepted unlimited POSTs from an authenticated session;
a stolen access token could be replayed in a tight loop to brute-force
confirm_password drift, churn bcrypt hash slots, or flood DB writes. We cap
at 5/minute per real client IP — same shape as the rest of /auth/*.

In the dev container the slowapi limiter is Redis-backed
(`USE_REDIS_RATE_LIMIT=true`), so bucket state persists across pytest
runs. We give every invocation a uniquely-derived TEST-NET-3 octet
(`time.monotonic_ns()`-based) so buckets are guaranteed-fresh regardless
of whether previous runs left counters in Redis.
"""
import time

import pytest


# AUD3-16: include current_password == password so every repeated call stays a
# valid no-op set (1st call = first-time set, current ignored; later calls =
# change with matching current) and the rate-limit assertions (5×200, then 429)
# still hold under the proof-of-presence guard.
VALID_BODY = {
    "password": "GoodPassword123",
    "confirm_password": "GoodPassword123",
    "current_password": "GoodPassword123",
}


def _unique_ip(salt: int = 0) -> str:
    """A reserved TEST-NET-3 IP (203.0.113.0/24, RFC 5737) whose last
    octet rotates per pytest invocation. Distinct salts within one test
    give independent buckets; one test's IPs never collide with another
    test's IPs."""
    base = (time.monotonic_ns() >> 4) & 0xFF
    octet = (base + salt) % 256
    # 0 and 255 sometimes get treated specially by tooling — squeeze the
    # range to [1, 254] to stay safe.
    if octet in (0, 255):
        octet = 1
    return f"203.0.113.{octet}"


@pytest.mark.asyncio
async def test_set_password_rate_limited_at_5_per_minute(client):
    """Six rapid POSTs from one IP: calls 1–5 succeed, 6th returns 429."""
    headers = {"X-Real-IP": _unique_ip(0)}

    for i in range(5):
        r = await client.post("/api/v2/auth/set-password", json=VALID_BODY, headers=headers)
        assert r.status_code == 200, f"call {i+1} expected 200, got {r.status_code}: {r.text}"

    r = await client.post("/api/v2/auth/set-password", json=VALID_BODY, headers=headers)
    assert r.status_code == 429, r.text


@pytest.mark.asyncio
async def test_set_password_per_ip_isolation(client):
    """A different real client IP gets its own bucket — limit is per-IP,
    not global. The two IPs differ by `salt` so they map to distinct
    octets but stay derived from the same time-bucket as above."""
    ip_a = {"X-Real-IP": _unique_ip(50)}
    ip_b = {"X-Real-IP": _unique_ip(120)}
    assert ip_a["X-Real-IP"] != ip_b["X-Real-IP"]

    for _ in range(5):
        await client.post("/api/v2/auth/set-password", json=VALID_BODY, headers=ip_a)

    # ip_a exhausted; ip_b still has its full quota.
    r = await client.post("/api/v2/auth/set-password", json=VALID_BODY, headers=ip_b)
    assert r.status_code == 200, r.text
