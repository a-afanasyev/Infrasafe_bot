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
                message="Перегрузка трансформатора", omit_type=False,
                reopen_sequence=None, reopen_chain_id=None,
                related_request_number=None, uk_urgency_override=None,
                uk_category_override=None, engineer_required_reason=None):
    alert = {"external_id": external_id, "type": alert_type,
             "severity": severity, "message": message}
    if omit_type:
        del alert["type"]
    # Sprint 10 / INT-120 — fields nest INSIDE the `alert` block to match
    # deployed wire (alertForwarder.js:199-226). The spec §2.2 example shows
    # them top-level — known doc drift, wire wins.
    if reopen_sequence is not None:
        alert["reopen_sequence"] = reopen_sequence
    if reopen_chain_id is not None:
        alert["reopen_chain_id"] = reopen_chain_id
    if related_request_number is not None:
        alert["related_request_number"] = related_request_number
    if uk_urgency_override is not None:
        alert["uk_urgency_override"] = uk_urgency_override
    if uk_category_override is not None:
        alert["uk_category_override"] = uk_category_override
    if engineer_required_reason is not None:
        alert["engineer_required_reason"] = engineer_required_reason
    body = {
        "event_id": event_id, "event": event,
        "timestamp": "2026-05-22T12:00:00Z", "alert": alert,
    }
    return json.dumps(body).encode()


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
    assert req.urgency == "low"                  # WARNING → low (TASK 17)
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
    assert req.urgency == "high"


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


# ── INT-120 (Sprint 10) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reopen_sequence_prefixes_description(
    webhook_client, building, db_session, monkeypatch,
):
    """When InfraSafe sets reopen_sequence ≥ 2 the request description gets
    a «Повторное обращение №N. {original}» prefix so dispatchers see the
    reopen context at a glance."""
    _set_secrets(monkeypatch)
    raw = _alert_body(
        "evt-reopen-2", _expected_external_id(building.id),
        alert_type="LEAK_DETECTED", severity="WARNING",
        message="После закрытия датчик снова показывает воду",
        reopen_sequence=2, reopen_chain_id="chain-f3a1c-uuid",
        related_request_number="260523-004",
    )
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.10"))
    assert r.status_code == 202
    req = await db_session.get(Request, r.json()["request_number"])
    assert req.description.startswith("Повторное обращение №2. ")
    assert "После закрытия датчик снова показывает воду" in req.description


@pytest.mark.asyncio
async def test_no_reopen_sequence_no_prefix(
    webhook_client, building, db_session, monkeypatch,
):
    """First-time alerts (Sprint 9 baseline shape) keep the description as-is —
    no «Повторное обращение» marker."""
    _set_secrets(monkeypatch)
    raw = _alert_body(
        "evt-firsttime", _expected_external_id(building.id),
        message="Утечка в стояке",
    )
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.11"))
    assert r.status_code == 202
    req = await db_session.get(Request, r.json()["request_number"])
    assert req.description == "Утечка в стояке"
    assert "Повторное" not in req.description


@pytest.mark.asyncio
async def test_uk_urgency_override_takes_precedence(
    webhook_client, building, db_session, monkeypatch,
):
    """When InfraSafe sends `uk_urgency_override`, UK trusts it as the
    resolved urgency — bypassing the SEVERITY_TO_URGENCY mapping."""
    _set_secrets(monkeypatch)
    # severity=WARNING would normally map to "Обычная" — override should win.
    raw = _alert_body(
        "evt-override", _expected_external_id(building.id),
        alert_type="LEAK_DETECTED", severity="WARNING",
        reopen_sequence=2, uk_urgency_override="Критическая",
    )
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.12"))
    assert r.status_code == 202
    req = await db_session.get(Request, r.json()["request_number"])
    assert req.urgency == "critical"


@pytest.mark.asyncio
async def test_uk_urgency_override_accepts_canonical_key(
    webhook_client, building, db_session, monkeypatch,
):
    """TASK 17: партнёр после миграции шлёт override ключом — UK принимает его как есть."""
    _set_secrets(monkeypatch)
    raw = _alert_body(
        "evt-override-key", _expected_external_id(building.id),
        alert_type="LEAK_DETECTED", severity="WARNING",
        reopen_sequence=2, uk_urgency_override="critical",
    )
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.13"))
    assert r.status_code == 202
    req = await db_session.get(Request, r.json()["request_number"])
    assert req.urgency == "critical"


@pytest.mark.asyncio
async def test_uk_urgency_override_outside_ladder_falls_back(
    webhook_client, building, db_session, monkeypatch,
):
    """Defensive: if InfraSafe ever sends a value outside the canonical ladder
    (config drift, new tier they haven't told us about), we don't 422 the
    request — we fall back to SEVERITY_TO_URGENCY and log a warning. Spec
    §2.2 phrases it «UK SHOULD use this value», not MUST."""
    _set_secrets(monkeypatch)
    raw = _alert_body(
        "evt-override-bad", _expected_external_id(building.id),
        alert_type="LEAK_DETECTED", severity="CRITICAL",  # → "Срочная"
        reopen_sequence=2, uk_urgency_override="ЧтоТоНеИзЛестницы",
    )
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.18"))
    assert r.status_code == 202
    req = await db_session.get(Request, r.json()["request_number"])
    # Fell back to severity mapping (CRITICAL → Срочная), NOT the bad override.
    assert req.urgency == "high"


@pytest.mark.asyncio
async def test_reopen_metadata_persisted_in_inbox(
    webhook_client, building, db_session, monkeypatch,
):
    """Reopen-chain metadata is stored in webhook_inbox.payload so the UI
    enrichment endpoint (FE/INT-120 sub-task #3) can surface it later."""
    _set_secrets(monkeypatch)
    raw = _alert_body(
        "evt-meta", _expected_external_id(building.id),
        reopen_sequence=3, reopen_chain_id="chain-abc",
        related_request_number="260523-009", uk_urgency_override="Срочная",
    )
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.13"))
    assert r.status_code == 202

    inbox = await db_session.scalar(
        select(WebhookInbox).where(WebhookInbox.event_id == "evt-meta")
    )
    # Per deployed wire (alertForwarder.js:199-226) the fields are nested
    # inside the `alert` block — webhook_inbox.payload preserves that shape.
    assert inbox.payload["alert"]["reopen_sequence"] == 3
    assert inbox.payload["alert"]["reopen_chain_id"] == "chain-abc"
    assert inbox.payload["alert"]["related_request_number"] == "260523-009"
    assert inbox.payload["alert"]["uk_urgency_override"] == "Срочная"


@pytest.mark.asyncio
async def test_outbound_webhook_carries_reopen_description(
    webhook_client, building, db_session, monkeypatch,
):
    """The outbound request.created webhook back to InfraSafe should carry
    the prefixed description — so their side sees the same operator-facing
    text we recorded locally."""
    _set_secrets(monkeypatch)
    raw = _alert_body(
        "evt-out-reopen", _expected_external_id(building.id),
        reopen_sequence=2, message="Опять течь",
    )
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.14"))
    assert r.status_code == 202

    # SQLite test dialect lacks JSONB path operators (`.astext`), so filter
    # the source_event_id in Python after pulling the small result set.
    rows = (await db_session.execute(
        select(WebhookOutbox).where(WebhookOutbox.event == "request.created")
    )).scalars().all()
    match = next(
        (row for row in rows
         if row.payload.get("request", {}).get("source_event_id") == "evt-out-reopen"),
        None,
    )
    assert match is not None
    assert match.payload["request"]["description"] == "Повторное обращение №2. Опять течь"


# ── INT-120 sub-task #2 (alert.engineer_required) ────────────────────

@pytest.mark.asyncio
async def test_engineer_required_routes_to_engineering_queue(
    webhook_client, building, db_session, monkeypatch,
):
    """`alert.engineer_required` produces a request in the engineering queue
    (category=«Инженерный разбор», urgency=«Критическая») — fixed per Sprint 10
    spec §2.4. Severity / uk_urgency_override do not apply to this event."""
    _set_secrets(monkeypatch)
    raw = _alert_body(
        "evt-engreq", _expected_external_id(building.id),
        event="alert.engineer_required",
        alert_type="LEAK_DETECTED", severity="WARNING",
        message="Цепь алертов не закрылась после 3 заявок",
        reopen_sequence=4, reopen_chain_id="chain-f3a1c-uuid",
        related_request_number="260523-006",
        uk_urgency_override="Срочная",  # MUST be ignored for this event type
        engineer_required_reason="max_reopens_per_24h",
    )
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.15"))
    assert r.status_code == 202

    req = await db_session.get(Request, r.json()["request_number"])
    assert req is not None
    assert req.category == "Инженерный разбор"
    assert req.urgency == "critical"
    # Reopen-marker prefix from sub-task #1 still works on engineer_required.
    assert req.description.startswith("Повторное обращение №4. ")


@pytest.mark.asyncio
async def test_engineer_required_persists_reason_in_inbox(
    webhook_client, building, db_session, monkeypatch,
):
    """`engineer_required_reason` lands in webhook_inbox.payload for ops audit
    (no business logic depends on the value — InfraSafe owns the reason
    vocabulary)."""
    _set_secrets(monkeypatch)
    raw = _alert_body(
        "evt-engreq-reason", _expected_external_id(building.id),
        event="alert.engineer_required",
        engineer_required_reason="max_reopens_per_24h",
        reopen_sequence=4,
    )
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.16"))
    assert r.status_code == 202

    inbox = await db_session.scalar(
        select(WebhookInbox).where(WebhookInbox.event_id == "evt-engreq-reason")
    )
    assert inbox.outcome == "accepted"
    assert inbox.payload["alert"]["engineer_required_reason"] == "max_reopens_per_24h"


@pytest.mark.asyncio
async def test_engineer_required_emits_outbound_request_created(
    webhook_client, building, db_session, monkeypatch,
):
    """`alert.engineer_required` triggers the same outbound `request.created`
    webhook back to InfraSafe so they can link source_event_id → engineering
    request_number for chain-tail accounting."""
    _set_secrets(monkeypatch)
    raw = _alert_body(
        "evt-engreq-out", _expected_external_id(building.id),
        event="alert.engineer_required",
        reopen_sequence=4, engineer_required_reason="max_reopens_per_24h",
    )
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.17"))
    assert r.status_code == 202

    rows = (await db_session.execute(
        select(WebhookOutbox).where(WebhookOutbox.event == "request.created")
    )).scalars().all()
    match = next(
        (row for row in rows
         if row.payload.get("request", {}).get("source_event_id") == "evt-engreq-out"),
        None,
    )
    assert match is not None
    assert match.payload["request"]["category"] == "Инженерный разбор"
    assert match.payload["request"]["urgency"] == "critical"  # outbound несёт ключ (TASK 17)


# ── INT-120 #1b — uk_category_override (InfraSafe PR #56) ────────────

@pytest.mark.asyncio
async def test_uk_category_override_replaces_type_mapping(
    webhook_client, building, db_session, monkeypatch,
):
    """When InfraSafe sends `uk_category_override`, it wins over the local
    TYPE_TO_CATEGORY mapping. Same SHOULD-not-MUST principle as urgency."""
    _set_secrets(monkeypatch)
    # LEAK_DETECTED would normally → "Сантехника"; override should win.
    raw = _alert_body(
        "evt-cat-override", _expected_external_id(building.id),
        alert_type="LEAK_DETECTED", severity="WARNING",
        uk_category_override="Безопасность",
    )
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.19"))
    assert r.status_code == 202
    req = await db_session.get(Request, r.json()["request_number"])
    assert req.category == "Безопасность"


@pytest.mark.asyncio
async def test_uk_category_override_wins_on_engineer_required(
    webhook_client, building, db_session, monkeypatch,
):
    """InfraSafe PR #56 sends `uk_category_override` even on engineer_required
    events. UK must honor it instead of the engineer-required hardcode — keeps
    InfraSafe in control of the chain-end taxonomy.

    In practice the override matches the hardcode («Инженерный разбор») so the
    observable category is identical; test asserts the override branch is
    actually taken by sending an unusual value."""
    _set_secrets(monkeypatch)
    raw = _alert_body(
        "evt-cat-override-engreq", _expected_external_id(building.id),
        event="alert.engineer_required",
        reopen_sequence=4,
        uk_category_override="Особый разбор",  # not the hardcoded value
        engineer_required_reason="max_reopens_per_24h",
    )
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.20"))
    assert r.status_code == 202
    req = await db_session.get(Request, r.json()["request_number"])
    assert req.category == "Особый разбор"
    # Urgency hardcode still applies (no urgency override sent here).
    assert req.urgency == "critical"


@pytest.mark.asyncio
async def test_uk_category_override_blank_falls_back(
    webhook_client, building, db_session, monkeypatch,
):
    """Defensive: blank/whitespace override → fall back to derived category."""
    _set_secrets(monkeypatch)
    raw = _alert_body(
        "evt-cat-blank", _expected_external_id(building.id),
        alert_type="LEAK_DETECTED", severity="WARNING",
        uk_category_override="   ",
    )
    r = await webhook_client.post(URL, content=raw, headers=_signed(raw, "203.0.114.21"))
    assert r.status_code == 202
    req = await db_session.get(Request, r.json()["request_number"])
    assert req.category == "Сантехника"  # fell back to TYPE_TO_CATEGORY
