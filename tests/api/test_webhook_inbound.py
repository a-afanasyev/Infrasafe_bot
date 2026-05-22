"""FIX-007 Phase 1 — inbound webhook receiver (InfraSafe → UK) security envelope.

Covers the full response matrix: 401 (no/bad/stale signature), 503 (no secret),
422 (bad schema), 409 (replay), 429 (rate-limit), 202 (accepted, dual-secret).
"""
import hashlib
import hmac
import json
import time

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from uk_management_bot.api.main import app
from uk_management_bot.api.webhooks import router as router_module
from uk_management_bot.config.settings import settings

URL = "/api/v2/webhooks/infrasafe/alert"
TEST_SECRET = "test_uk_webhook_secret_primary"
TEST_SECRET_NEXT = "test_uk_webhook_secret_next"


# ── helpers ──────────────────────────────────────────────────────────

def _body(event_id: str = "evt-1") -> bytes:
    return json.dumps({
        "event_id": event_id,
        "event": "alert.created",
        "timestamp": "2026-05-22T10:00:00Z",
        "alert": {"severity": "high", "message": "boiler offline"},
    }).encode()


def _sign(raw: bytes, secret: str, ts: int | None = None) -> str:
    """Build an `x-webhook-signature` header — mirrors webhook_sender.sign_payload."""
    ts = ts if ts is not None else int(time.time())
    message = f"{ts}.".encode() + raw
    sig = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _set_secrets(monkeypatch, primary: str = TEST_SECRET, nxt: str = TEST_SECRET_NEXT):
    monkeypatch.setattr(settings, "UK_WEBHOOK_SECRET", primary)
    monkeypatch.setattr(settings, "UK_WEBHOOK_SECRET_NEXT", nxt)


# ── fixtures ─────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def webhook_client():
    """HTTP client for the webhook endpoint — no DB, no auth overrides needed."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def _stub_replay(monkeypatch):
    """Default: every request is a fresh event (no Redis in the test env).

    The replay-specific test overrides this with a stateful fake.
    """
    async def _no_replay(event_id: str) -> bool:
        return False
    monkeypatch.setattr(router_module, "is_replay", _no_replay)


# ── 401 — signature failures ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_signature_header(webhook_client, monkeypatch):
    _set_secrets(monkeypatch)
    r = await webhook_client.post(URL, content=_body(), headers={"X-Real-IP": "203.0.113.1"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_bad_format_header(webhook_client, monkeypatch):
    _set_secrets(monkeypatch)
    r = await webhook_client.post(
        URL, content=_body(),
        headers={"x-webhook-signature": "t=123", "X-Real-IP": "203.0.113.2"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_invalid_signature(webhook_client, monkeypatch):
    _set_secrets(monkeypatch)
    r = await webhook_client.post(
        URL, content=_body(),
        headers={"x-webhook-signature": f"t={int(time.time())},v1=deadbeef",
                 "X-Real-IP": "203.0.113.3"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_stale_timestamp(webhook_client, monkeypatch):
    _set_secrets(monkeypatch)
    raw = _body()
    sig = _sign(raw, TEST_SECRET, ts=int(time.time()) - 400)  # outside 300s window
    r = await webhook_client.post(
        URL, content=raw,
        headers={"x-webhook-signature": sig, "X-Real-IP": "203.0.113.4"},
    )
    assert r.status_code == 401


# ── 202 — accepted (dual-secret) ─────────────────────────────────────

@pytest.mark.asyncio
async def test_valid_signature_primary_secret(webhook_client, monkeypatch):
    _set_secrets(monkeypatch)
    raw = _body()
    sig = _sign(raw, TEST_SECRET)
    r = await webhook_client.post(
        URL, content=raw,
        headers={"x-webhook-signature": sig, "X-Real-IP": "203.0.113.5"},
    )
    assert r.status_code == 202
    assert r.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_valid_signature_next_secret(webhook_client, monkeypatch):
    """Dual-secret rotation — a signature made with UK_WEBHOOK_SECRET_NEXT passes."""
    _set_secrets(monkeypatch)
    raw = _body()
    sig = _sign(raw, TEST_SECRET_NEXT)
    r = await webhook_client.post(
        URL, content=raw,
        headers={"x-webhook-signature": sig, "X-Real-IP": "203.0.113.6"},
    )
    assert r.status_code == 202


# ── 409 — replay ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_replay_returns_409(webhook_client, monkeypatch):
    _set_secrets(monkeypatch)
    seen: set[str] = set()

    async def _stateful_replay(event_id: str) -> bool:
        duplicate = event_id in seen
        seen.add(event_id)
        return duplicate

    monkeypatch.setattr(router_module, "is_replay", _stateful_replay)

    raw = _body("evt-replay")
    sig = _sign(raw, TEST_SECRET)
    headers = {"x-webhook-signature": sig, "X-Real-IP": "203.0.113.7"}

    first = await webhook_client.post(URL, content=raw, headers=headers)
    second = await webhook_client.post(URL, content=raw, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 409


# ── 422 — bad schema ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_schema(webhook_client, monkeypatch):
    """Valid signature, but the body is missing the required `event_id`."""
    _set_secrets(monkeypatch)
    raw = json.dumps({"event": "alert.created", "timestamp": "t", "alert": {}}).encode()
    sig = _sign(raw, TEST_SECRET)
    r = await webhook_client.post(
        URL, content=raw,
        headers={"x-webhook-signature": sig, "X-Real-IP": "203.0.113.8"},
    )
    assert r.status_code == 422


# ── 503 — misconfiguration ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_secret_configured(webhook_client, monkeypatch):
    _set_secrets(monkeypatch, primary="", nxt="")
    raw = _body()
    r = await webhook_client.post(
        URL, content=raw,
        headers={"x-webhook-signature": _sign(raw, "anything"),
                 "X-Real-IP": "203.0.113.9"},
    )
    assert r.status_code == 503


# ── 429 — rate-limit ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rate_limit_60_per_minute(webhook_client, monkeypatch):
    """61 requests from one IP within a minute → the 61st is 429.

    Requests are unsigned (each is a 401) — the limiter counts every call to the
    route regardless of outcome. A unique X-Real-IP isolates this test's bucket.
    """
    _set_secrets(monkeypatch)
    headers = {"X-Real-IP": "203.0.113.99"}
    last = None
    for _ in range(61):
        last = await webhook_client.post(URL, content=_body(), headers=headers)
    assert last.status_code == 429
