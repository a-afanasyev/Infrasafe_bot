"""FIX-007 Phase 2 — inbound alert → UK request handler.

Covers: alert.created → request creation, dedup (409), non-alert no-op,
unknown building (422), invalid alert block (422), type/severity mapping,
and the outbound request.created webhook with source_event_id.
"""
import hashlib
import hmac
import json
import time

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from uk_management_bot.api.dependencies import get_db
from uk_management_bot.api.main import app
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.webhook_inbox import WebhookInbox
from uk_management_bot.database.models.webhook_outbox import WebhookOutbox
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.reconciliation import _expected_external_id

URL = "/api/v2/webhooks/infrasafe/alert"
TEST_SECRET = "test_uk_webhook_secret_primary"


# ── helpers ──────────────────────────────────────────────────────────

def _alert_body(event_id, external_id, *, event="alert.created",
                alert_type="TRANSFORMER_OVERLOAD", severity="CRITICAL",
                message="Перегрузка трансформатора", omit_type=False):
    alert = {"external_id": external_id, "type": alert_type,
             "severity": severity, "message": message}
    if omit_type:
        del alert["type"]
    return json.dumps({
        "event_id": event_id, "event": event,
        "timestamp": "2026-05-22T12:00:00Z", "alert": alert,
    }).encode()


def _signed(raw: bytes, ip: str, secret: str = TEST_SECRET) -> dict:
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
    return {"x-webhook-signature": f"t={ts},v1={sig}", "X-Real-IP": ip}


def _set_secrets(monkeypatch):
    monkeypatch.setattr(settings, "UK_WEBHOOK_SECRET", TEST_SECRET)
    monkeypatch.setattr(settings, "UK_WEBHOOK_SECRET_NEXT", "")


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


@pytest_asyncio.fixture
async def building(db_session):
    """Seed a yard, a building and the InfraSafe system user (migration 009)."""
    yard = Yard(name="Тестовый двор")
    db_session.add(yard)
    await db_session.flush()
    b = Building(address="ул. Тестовая, 1", yard_id=yard.id, is_active=True)
    sysuser = User(
        telegram_id=settings.INFRASAFE_SYSTEM_USER_TELEGRAM_ID,
        first_name="InfraSafe", role="manager", roles='["manager"]',
        active_role="manager", status="approved",
    )
    db_session.add_all([b, sysuser])
    await db_session.commit()
    await db_session.refresh(b)
    return b


@pytest.fixture(autouse=True)
def _stub_replay(monkeypatch):
    """Redis is unavailable in tests — stub the fast-guard (webhook_inbox is the
    authoritative dedup anyway)."""
    async def _no_replay(event_id: str) -> bool:
        return False
    monkeypatch.setattr("uk_management_bot.services.inbound_alert.is_replay", _no_replay)


# ── tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_alert_created_creates_request(webhook_client, building, db_session, monkeypatch):
    _set_secrets(monkeypatch)
    raw = _alert_body("evt-create", _expected_external_id(building.id),
                      alert_type="LEAK_DETECTED", severity="WARNING")
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.1"))
    assert r.status_code == 202
    rn = r.json()["request_number"]

    req = await db_session.get(Request, rn)
    assert req is not None
    assert req.category == "Сантехника"          # LEAK_DETECTED → Сантехника
    assert req.urgency == "Обычная"              # WARNING → Обычная
    assert req.apartment_id is None              # building-level
    assert req.address == building.address
    assert req.description == "Перегрузка трансформатора"
    sysuser = await db_session.scalar(
        select(User).where(User.telegram_id == settings.INFRASAFE_SYSTEM_USER_TELEGRAM_ID)
    )
    assert req.user_id == sysuser.id


@pytest.mark.asyncio
async def test_duplicate_event_returns_409(webhook_client, building, monkeypatch):
    _set_secrets(monkeypatch)
    raw = _alert_body("evt-dup", _expected_external_id(building.id))
    h = _signed(raw, "203.0.114.2")
    first = await webhook_client.post(URL, content=raw, headers=h)
    second = await webhook_client.post(URL, content=raw, headers=h)
    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["request_number"] == first.json()["request_number"]


@pytest.mark.asyncio
async def test_non_alert_event_ignored(webhook_client, building, db_session, monkeypatch):
    _set_secrets(monkeypatch)
    raw = _alert_body("evt-resolved", _expected_external_id(building.id),
                      event="alert.resolved")
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.3"))
    assert r.status_code == 202
    assert r.json()["status"] == "ignored"

    requests = (await db_session.execute(select(Request))).scalars().all()
    assert requests == []
    inbox = await db_session.scalar(
        select(WebhookInbox).where(WebhookInbox.event_id == "evt-resolved")
    )
    assert inbox.outcome == "ignored"


@pytest.mark.asyncio
async def test_unknown_building_returns_422(webhook_client, building, monkeypatch):
    _set_secrets(monkeypatch)
    raw = _alert_body("evt-unknown", "00000000-0000-4000-8000-000000000000")
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.4"))
    assert r.status_code == 422
    assert "building" in r.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_alert_block_returns_422(webhook_client, building, monkeypatch):
    _set_secrets(monkeypatch)
    raw = _alert_body("evt-badblock", _expected_external_id(building.id), omit_type=True)
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.5"))
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_unknown_type_falls_back_to_other(webhook_client, building, db_session, monkeypatch):
    _set_secrets(monkeypatch)
    raw = _alert_body("evt-unk-type", _expected_external_id(building.id),
                      alert_type="SOME_FUTURE_TYPE")
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.6"))
    assert r.status_code == 202
    req = await db_session.get(Request, r.json()["request_number"])
    assert req.category == "Другое"


@pytest.mark.asyncio
async def test_critical_severity_maps_to_urgent(webhook_client, building, db_session, monkeypatch):
    _set_secrets(monkeypatch)
    raw = _alert_body("evt-crit", _expected_external_id(building.id), severity="CRITICAL")
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.7"))
    assert r.status_code == 202
    req = await db_session.get(Request, r.json()["request_number"])
    assert req.urgency == "Срочная"


@pytest.mark.asyncio
async def test_request_created_webhook_emitted(webhook_client, building, db_session, monkeypatch):
    _set_secrets(monkeypatch)
    raw = _alert_body("evt-webhook", _expected_external_id(building.id))
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.8"))
    assert r.status_code == 202

    outbox = (await db_session.execute(
        select(WebhookOutbox).where(WebhookOutbox.event == "request.created")
    )).scalars().all()
    assert len(outbox) == 1
    assert outbox[0].payload["request"]["source_event_id"] == "evt-webhook"
    assert outbox[0].payload["request"]["request_number"] == r.json()["request_number"]
