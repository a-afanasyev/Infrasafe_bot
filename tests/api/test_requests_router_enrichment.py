"""INT-120 #3 — GET /api/v2/requests/{number} surfaces reopen-meta.

Inbound alerts from InfraSafe carry optional Sprint 10 reopen-chain metadata
in `webhook_inbox.payload.alert.*`. The dispatcher view needs four of those
fields surfaced on the request card so the UI (sub-task #4) can render
«Повторное обращение №N» badge + chain link.

Source-of-truth: the most recent **accepted** `webhook_inbox` row for the
request (request_number is unique enough on prod that there's exactly one
inbox row per infrasafe-originated request — but we order by id DESC and
LIMIT 1 defensively).
"""
import pytest
import pytest_asyncio

from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.webhook_inbox import WebhookInbox


URL_TPL = "/api/v2/requests/{rn}"


# ── Helpers ──────────────────────────────────────────────────────────

async def _seed_request(db_session, rn: str, *, source: str = "infrasafe",
                        category: str = "Сантехника", urgency: str = "Срочная",
                        description: str = "test request"):
    req = RequestModel(
        request_number=rn,
        user_id=999999,  # the test manager seeded in conftest
        category=category,
        urgency=urgency,
        description=description,
        address="ул. Тестовая, 1",
        apartment_id=None,
        status="Новая",
        source=source,
        media_files=[],
    )
    db_session.add(req)
    await db_session.commit()
    await db_session.refresh(req)
    return req


async def _seed_inbox(db_session, *, request_number: str, event_id: str,
                      event: str = "alert.created", outcome: str = "accepted",
                      reopen_sequence=None, reopen_chain_id=None,
                      related_request_number=None, engineer_required_reason=None):
    alert = {
        "external_id": "test-ext",
        "type": "LEAK_DETECTED",
        "severity": "WARNING",
        "message": "x",
    }
    if reopen_sequence is not None:
        alert["reopen_sequence"] = reopen_sequence
    if reopen_chain_id is not None:
        alert["reopen_chain_id"] = reopen_chain_id
    if related_request_number is not None:
        alert["related_request_number"] = related_request_number
    if engineer_required_reason is not None:
        alert["engineer_required_reason"] = engineer_required_reason

    row = WebhookInbox(
        event_id=event_id,
        event=event,
        source_ip="203.0.114.1",
        payload={
            "event_id": event_id,
            "event": event,
            "timestamp": "2026-05-24T07:00:00Z",
            "alert": alert,
        },
        outcome=outcome,
        request_number=request_number,
    )
    db_session.add(row)
    await db_session.commit()


# ── Tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reopen_meta_surfaced_on_alert_created(client, db_session, manager_user):
    """An infrasafe-originated request created by a Sprint 10 reopen-event
    (reopen_sequence ≥ 2) surfaces the 4 reopen-meta fields via the GET endpoint."""
    await _seed_request(db_session, "260524-100")
    await _seed_inbox(
        db_session, request_number="260524-100", event_id="evt-100",
        reopen_sequence=2, reopen_chain_id="chain-uuid-100",
        related_request_number="260524-099",
    )

    r = await client.get(URL_TPL.format(rn="260524-100"))
    assert r.status_code == 200
    body = r.json()
    assert body["request_number"] == "260524-100"
    assert body["reopen_sequence"] == 2
    assert body["reopen_chain_id"] == "chain-uuid-100"
    assert body["related_request_number"] == "260524-099"
    # No engineer_required_reason on regular alert.created reopen.
    assert body["engineer_required_reason"] is None


@pytest.mark.asyncio
async def test_engineer_required_reason_surfaced(client, db_session, manager_user):
    """`alert.engineer_required` events also store engineer_required_reason in
    inbox.payload — surface it for the dispatcher UI."""
    await _seed_request(
        db_session, "260524-101",
        category="Инженерный разбор", urgency="Критическая",
    )
    await _seed_inbox(
        db_session, request_number="260524-101", event_id="evt-101",
        event="alert.engineer_required",
        reopen_sequence=4, reopen_chain_id="chain-uuid-101",
        related_request_number="260524-100",
        engineer_required_reason="max_reopens_per_24h",
    )

    r = await client.get(URL_TPL.format(rn="260524-101"))
    assert r.status_code == 200
    body = r.json()
    assert body["reopen_sequence"] == 4
    assert body["engineer_required_reason"] == "max_reopens_per_24h"
    assert body["related_request_number"] == "260524-100"


@pytest.mark.asyncio
async def test_manual_request_no_inbox_returns_null_meta(client, db_session, manager_user):
    """A request created via the UK dashboard (no webhook_inbox row) returns
    null/None for all 4 reopen-meta fields — no surprises."""
    await _seed_request(db_session, "260524-102", source="web")

    r = await client.get(URL_TPL.format(rn="260524-102"))
    assert r.status_code == 200
    body = r.json()
    assert body["reopen_sequence"] is None
    assert body["reopen_chain_id"] is None
    assert body["related_request_number"] is None
    assert body["engineer_required_reason"] is None


@pytest.mark.asyncio
async def test_sprint9_baseline_no_reopen_meta(client, db_session, manager_user):
    """Sprint 9 baseline payloads contained `reopen_sequence=1` (per deployed
    wire `|| 1` default). UK considers seq=1 == first-time alert (no reopen),
    so the GET endpoint surfaces null for reopen_sequence regardless.

    (We don't filter on the wire/storage side — inbox.payload keeps the raw
    value for audit — but the API response treats sequence=1 as "no reopen"
    to align with the contract.)
    """
    await _seed_request(db_session, "260524-103")
    await _seed_inbox(
        db_session, request_number="260524-103", event_id="evt-103",
        reopen_sequence=1,  # first-time alert per deployed wire
    )

    r = await client.get(URL_TPL.format(rn="260524-103"))
    assert r.status_code == 200
    body = r.json()
    # Spec §2.2: «only on reopens (and only when ≥ 2)». seq=1 → suppress.
    assert body["reopen_sequence"] is None
    assert body["reopen_chain_id"] is None


@pytest.mark.asyncio
async def test_inbox_with_no_reopen_keys_returns_null(client, db_session, manager_user):
    """If an inbox row exists but the alert block has no reopen keys at all
    (legacy pre-Sprint-10 payload), the surface fields are null."""
    await _seed_request(db_session, "260524-104")
    await _seed_inbox(
        db_session, request_number="260524-104", event_id="evt-104",
        # No reopen_* args — alert dict has only the 4 required fields.
    )

    r = await client.get(URL_TPL.format(rn="260524-104"))
    assert r.status_code == 200
    body = r.json()
    assert body["reopen_sequence"] is None
    assert body["reopen_chain_id"] is None
    assert body["related_request_number"] is None
    assert body["engineer_required_reason"] is None
