"""FIX-007 — inbound webhook receiver (InfraSafe → UK) security envelope.

Covers the envelope layer: 401 (no/bad/stale signature), 503 (no secret),
422 (bad envelope schema), 429 (rate-limit), 202 (signature OK → handler).
The alert→request handler itself is covered by test_inbound_alert.py.
"""
import hashlib
import hmac
import json
import time

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from uk_management_bot.api.dependencies import get_db
from uk_management_bot.api.main import app
from uk_management_bot.config.settings import settings

URL = "/api/v2/webhooks/infrasafe/alert"
TEST_SECRET = "test_uk_webhook_secret_primary"
TEST_SECRET_NEXT = "test_uk_webhook_secret_next"


# ── helpers ──────────────────────────────────────────────────────────

def _body(event_id: str = "evt-1", event: str = "alert.acknowledged") -> bytes:
    """A signature-valid envelope. Uses a non-alert.created event so the handler
    no-ops (202 ignored) without needing a seeded building."""
    return json.dumps({
        "event_id": event_id,
        "event": event,
        "timestamp": "2026-05-22T10:00:00Z",
        "alert": {"note": "envelope test"},
    }).encode()


def _sign(raw: bytes, secret: str, ts: int | None = None) -> str:
    ts = ts if ts is not None else int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _set_secrets(monkeypatch, primary: str = TEST_SECRET, nxt: str = TEST_SECRET_NEXT):
    monkeypatch.setattr(settings, "UK_WEBHOOK_SECRET", primary)
    monkeypatch.setattr(settings, "UK_WEBHOOK_SECRET_NEXT", nxt)


# ── fixtures ─────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def webhook_client(db_session_factory):
    async def override_get_db():
        async with db_session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _stub_replay(monkeypatch):
    """Redis is unavailable in tests — stub the handler's fast-guard."""
    async def _no_replay(event_id: str) -> bool:
        return False
    monkeypatch.setattr("uk_management_bot.services.inbound_alert.is_replay", _no_replay)


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


# ── 202 — signature OK, handler reached (dual-secret) ────────────────

@pytest.mark.asyncio
async def test_valid_signature_primary_secret(webhook_client, monkeypatch):
    _set_secrets(monkeypatch)
    raw = _body("evt-envelope-1")
    sig = _sign(raw, TEST_SECRET)
    r = await webhook_client.post(
        URL, content=raw,
        headers={"x-webhook-signature": sig, "X-Real-IP": "203.0.113.5"},
    )
    assert r.status_code == 202


@pytest.mark.asyncio
async def test_valid_signature_next_secret(webhook_client, monkeypatch):
    """Dual-secret rotation — a signature made with UK_WEBHOOK_SECRET_NEXT passes."""
    _set_secrets(monkeypatch)
    raw = _body("evt-envelope-2")
    sig = _sign(raw, TEST_SECRET_NEXT)
    r = await webhook_client.post(
        URL, content=raw,
        headers={"x-webhook-signature": sig, "X-Real-IP": "203.0.113.6"},
    )
    assert r.status_code == 202


# ── 422 — bad envelope schema ────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_envelope_schema(webhook_client, monkeypatch):
    """Valid signature, but the envelope is missing the required `event_id`."""
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
    """61 unsigned requests from one IP within a minute → the 61st is 429.

    Requests are unsigned (each is a 401) — the limiter counts every call.
    A unique X-Real-IP isolates this test's bucket.
    """
    _set_secrets(monkeypatch)
    headers = {"X-Real-IP": "203.0.113.99"}
    last = None
    for _ in range(61):
        last = await webhook_client.post(URL, content=_body(), headers=headers)
    assert last.status_code == 429
