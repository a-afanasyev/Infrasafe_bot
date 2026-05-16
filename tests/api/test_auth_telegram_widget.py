"""Endpoint tests for POST /api/v2/auth/telegram-widget.

Regression guard: the HMAC must be verified over the *raw* request body.
Routing it through the TelegramWidgetLogin pydantic model and calling
model_dump() injects None for any optional field Telegram omitted
(last_name / username / photo_url for users that don't have them) — those
Nones corrupt data_check_string and the hash check fails with 401.

These tests POST through the real ASGI app, so they exercise the pydantic
round-trip that the verify_telegram_widget unit tests bypass.
"""
import hashlib
import hmac
import time

import pytest

from uk_management_bot.config.settings import settings


def _sign(payload: dict) -> dict:
    """Return payload + a valid Telegram Widget hash for the current BOT_TOKEN."""
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(payload.items()))
    secret_key = hashlib.sha256(settings.BOT_TOKEN.encode()).digest()
    signed = dict(payload)
    signed["hash"] = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return signed


@pytest.mark.asyncio
async def test_widget_login_minimal_payload_succeeds(client, manager_user):
    """User without last_name/username/photo_url — Telegram omits those fields.

    Before the raw-body fix this 401'd: model_dump() added last_name=None etc.
    """
    if not settings.BOT_TOKEN:
        pytest.skip("BOT_TOKEN not set")

    payload = _sign({
        "id": manager_user.telegram_id,
        "first_name": "Test",
        "auth_date": int(time.time()),
    })

    resp = await client.post("/api/v2/auth/telegram-widget", json=payload)

    assert resp.status_code == 200, resp.text
    assert "access_token" in resp.json()
    set_cookie = resp.headers.get("set-cookie", "")
    assert "uk_access" in set_cookie
    assert "uk_refresh" in set_cookie


@pytest.mark.asyncio
async def test_widget_login_full_payload_succeeds(client, manager_user):
    """User with every optional field present also verifies."""
    if not settings.BOT_TOKEN:
        pytest.skip("BOT_TOKEN not set")

    payload = _sign({
        "id": manager_user.telegram_id,
        "first_name": "Test",
        "last_name": "Manager",
        "username": "testmanager",
        "photo_url": "https://t.me/i/userpic/320/x.jpg",
        "auth_date": int(time.time()),
    })

    resp = await client.post("/api/v2/auth/telegram-widget", json=payload)

    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_widget_login_bad_hash_rejected(client, manager_user):
    """Tampered payload must not authenticate."""
    payload = {
        "id": manager_user.telegram_id,
        "first_name": "Test",
        "auth_date": int(time.time()),
        "hash": "deadbeef" * 8,
    }

    resp = await client.post("/api/v2/auth/telegram-widget", json=payload)

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_widget_login_stale_auth_date_rejected(client, manager_user):
    """auth_date older than the 5-minute window (plan §7.4) is rejected."""
    if not settings.BOT_TOKEN:
        pytest.skip("BOT_TOKEN not set")

    payload = _sign({
        "id": manager_user.telegram_id,
        "first_name": "Test",
        "auth_date": int(time.time()) - 3600,
    })

    resp = await client.post("/api/v2/auth/telegram-widget", json=payload)

    assert resp.status_code == 401
