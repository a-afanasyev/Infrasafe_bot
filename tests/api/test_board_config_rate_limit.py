"""SEC-084 — write-side rate-limit on PUT /api/v2/board-config.

GET has 120/min; the manager-only PUT had no limit, so a stolen manager token
could churn config writes unbounded. PUT now caps at 30/min per real client IP.

Like the other limiter tests, we rotate a TEST-NET-3 IP per invocation so the
Redis-backed bucket in the dev container is always fresh.
"""
import time

import pytest

from uk_management_bot.api.board_config.defaults import DEFAULT_BOARD_CONFIG


def _unique_ip(salt: int = 0) -> str:
    base = (time.monotonic_ns() >> 4) & 0xFF
    octet = (base + salt) % 256
    if octet in (0, 255):
        octet = 1
    return f"203.0.113.{octet}"


@pytest.mark.asyncio
async def test_put_board_config_rate_limited_at_30_per_minute(client):
    headers = {"X-Real-IP": _unique_ip(0)}

    for i in range(30):
        r = await client.put("/api/v2/board-config", json=DEFAULT_BOARD_CONFIG, headers=headers)
        assert r.status_code == 200, f"call {i+1} expected 200, got {r.status_code}: {r.text}"

    r = await client.put("/api/v2/board-config", json=DEFAULT_BOARD_CONFIG, headers=headers)
    assert r.status_code == 429, r.text


@pytest.mark.asyncio
async def test_put_board_config_per_ip_isolation(client):
    ip_a = {"X-Real-IP": _unique_ip(40)}
    ip_b = {"X-Real-IP": _unique_ip(110)}
    assert ip_a["X-Real-IP"] != ip_b["X-Real-IP"]

    for _ in range(30):
        await client.put("/api/v2/board-config", json=DEFAULT_BOARD_CONFIG, headers=ip_a)

    # ip_a exhausted; ip_b still has its full quota.
    r = await client.put("/api/v2/board-config", json=DEFAULT_BOARD_CONFIG, headers=ip_b)
    assert r.status_code == 200, r.text
