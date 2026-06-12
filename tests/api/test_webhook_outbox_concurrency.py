"""PR-A/PR-5 — process_outbox() multi-worker safety (claim/lease + SKIP LOCKED).

The true 2-worker race can only be exercised against PostgreSQL (SQLite has no
row locking and SQLAlchemy silently drops FOR UPDATE for it) — see
test_webhook_outbox_pg_concurrency.py for the real-race suite. These sqlite
tests cover the dialect compilation and the claim/finalize state machine:

  1. The claim SELECT carries `FOR UPDATE SKIP LOCKED` on the PG dialect.
  2. process_outbox() delivers every pending record exactly once and does not
     double-send; success does NOT consume retry budget (attempts stays 0).
  3. CAS finalize: a stale claim_token never overwrites a reclaimed record.
  4. attempts increments only on confirmed failure; `failed` only after the
     last allowed attempt's result.
  5. Stale in_flight records are reclaimed after lease expiry.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from uk_management_bot.database.models.webhook_outbox import WebhookOutbox
from uk_management_bot.services import webhook_sender


def test_claim_select_compiles_with_skip_locked():
    """The claim query must emit FOR UPDATE SKIP LOCKED on PostgreSQL."""
    now = datetime.now(timezone.utc)
    stmt = webhook_sender._claimable_stmt(now, now - timedelta(seconds=200), 10)
    compiled = str(stmt.compile(dialect=postgresql.dialect())).upper()
    assert "FOR UPDATE SKIP LOCKED" in compiled


@pytest_asyncio.fixture
async def _outbox_env(db_session_factory, monkeypatch):
    """Wire process_outbox() onto the in-memory test DB with a mocked sender."""
    monkeypatch.setattr(
        "uk_management_bot.database.session.AsyncSessionLocal",
        db_session_factory,
    )
    monkeypatch.setattr(webhook_sender.settings, "INFRASAFE_WEBHOOK_ENABLED", True)
    monkeypatch.setattr(webhook_sender.settings, "INFRASAFE_WEBHOOK_URL", "http://infrasafe.test")
    monkeypatch.setattr(webhook_sender.settings, "INFRASAFE_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setattr(webhook_sender.settings, "INFRASAFE_USE_NEXT_SECRET", False)

    mock_send = AsyncMock(return_value=(True, "", False, 0))
    monkeypatch.setattr(webhook_sender, "send_webhook", mock_send)
    return db_session_factory, mock_send


def _pending_record(**overrides) -> WebhookOutbox:
    defaults = dict(
        event_id=str(uuid.uuid4()),
        event="building.created",
        endpoint="/api/webhooks/uk/building",
        payload={"event": "building.created"},
        status="pending",
    )
    defaults.update(overrides)
    return WebhookOutbox(**defaults)


@pytest.mark.asyncio
async def test_process_outbox_sends_each_record_once(_outbox_env):
    """100 pending records → exactly 100 sends; success does not touch attempts.

    process_outbox() claims batches of INFRASAFE_OUTBOX_CLAIM_BATCH up to ~50
    per cycle, so three cycles drain 100 records; a fourth proves no re-send.
    """
    db_session_factory, mock_send = _outbox_env

    async with db_session_factory() as db:
        for _ in range(100):
            db.add(_pending_record())
        await db.commit()

    for _ in range(4):
        await webhook_sender.process_outbox()

    assert mock_send.call_count == 100

    async with db_session_factory() as db:
        records = (await db.execute(select(WebhookOutbox))).scalars().all()
        assert len(records) == 100
        assert all(r.status == "sent" for r in records)
        # PR-5: retry budget расходуют только подтверждённые неуспехи.
        assert all(r.attempts == 0 for r in records)
        assert all(r.claim_count == 1 for r in records)
        assert all(r.claim_token is None for r in records)


@pytest.mark.asyncio
async def test_attempts_only_on_confirmed_failure_and_failed_on_last(_outbox_env):
    """Retryable failures consume attempts one by one; `failed` only after the
    result of the last allowed attempt (max_retries=3 → 3 confirmed failures)."""
    db_session_factory, mock_send = _outbox_env
    mock_send.return_value = (False, "HTTP 503: service unavailable", True, 0)

    async with db_session_factory() as db:
        db.add(_pending_record(event_id="evt-fail"))
        await db.commit()

    async def _get():
        async with db_session_factory() as db:
            return (await db.execute(
                select(WebhookOutbox).where(WebhookOutbox.event_id == "evt-fail")
            )).scalar_one()

    async def _clear_backoff():
        async with db_session_factory() as db:
            rec = (await db.execute(
                select(WebhookOutbox).where(WebhookOutbox.event_id == "evt-fail")
            )).scalar_one()
            rec.retry_after = None
            await db.commit()

    await webhook_sender.process_outbox()
    rec = await _get()
    assert (rec.status, rec.attempts) == ("pending", 1)

    await _clear_backoff()
    await webhook_sender.process_outbox()
    rec = await _get()
    assert (rec.status, rec.attempts) == ("pending", 2)

    await _clear_backoff()
    await webhook_sender.process_outbox()
    rec = await _get()
    # Третий подтверждённый неуспех = последняя разрешённая попытка → failed.
    assert (rec.status, rec.attempts) == ("failed", 3)
    assert mock_send.call_count == 3


@pytest.mark.asyncio
async def test_crash_does_not_consume_retry_budget(_outbox_env):
    """Unknown result (sender raises) → record returns to pending with
    attempts untouched; the same event_id is redelivered (at-least-once)."""
    db_session_factory, mock_send = _outbox_env
    mock_send.side_effect = RuntimeError("worker crashed mid-flight")

    async with db_session_factory() as db:
        db.add(_pending_record(event_id="evt-crash"))
        await db.commit()

    await webhook_sender.process_outbox()

    async with db_session_factory() as db:
        rec = (await db.execute(
            select(WebhookOutbox).where(WebhookOutbox.event_id == "evt-crash")
        )).scalar_one()
        assert rec.status == "pending"
        assert rec.attempts == 0          # budget NOT consumed
        assert rec.claim_count == 1       # observability counter did move
        assert rec.event_id == "evt-crash"  # same event_id for redelivery

    # Redelivery succeeds.
    mock_send.side_effect = None
    mock_send.return_value = (True, "", False, 0)
    await webhook_sender.process_outbox()

    async with db_session_factory() as db:
        rec = (await db.execute(
            select(WebhookOutbox).where(WebhookOutbox.event_id == "evt-crash")
        )).scalar_one()
        assert rec.status == "sent"
        assert rec.attempts == 0
        assert rec.claim_count == 2


@pytest.mark.asyncio
async def test_stale_in_flight_reclaimed_after_lease(_outbox_env):
    """in_flight older than lease is picked up again (new claim_token)."""
    db_session_factory, mock_send = _outbox_env
    lease = webhook_sender.settings.INFRASAFE_OUTBOX_LEASE_SECONDS

    stale_claim = str(uuid.uuid4())
    async with db_session_factory() as db:
        db.add(_pending_record(
            event_id="evt-stale",
            status="in_flight",
            claim_token=stale_claim,
            claimed_at=datetime.now(timezone.utc) - timedelta(seconds=lease + 60),
            claim_count=1,
        ))
        await db.commit()

    await webhook_sender.process_outbox()

    async with db_session_factory() as db:
        rec = (await db.execute(
            select(WebhookOutbox).where(WebhookOutbox.event_id == "evt-stale")
        )).scalar_one()
        assert rec.status == "sent"
        assert rec.claim_count == 2
        assert rec.claim_token is None


@pytest.mark.asyncio
async def test_fresh_in_flight_not_reclaimed(_outbox_env):
    """in_flight inside its lease window belongs to a живой воркер — не трогаем."""
    db_session_factory, mock_send = _outbox_env

    async with db_session_factory() as db:
        db.add(_pending_record(
            event_id="evt-fresh",
            status="in_flight",
            claim_token=str(uuid.uuid4()),
            claimed_at=datetime.now(timezone.utc),
            claim_count=1,
        ))
        await db.commit()

    await webhook_sender.process_outbox()
    assert mock_send.call_count == 0


@pytest.mark.asyncio
async def test_stale_finalize_discarded_by_cas(_outbox_env, db_session_factory):
    """CAS: финализация с устаревшим claim_token не перезаписывает запись,
    которую reclaim'нул (и финализировал) другой воркер."""
    async with db_session_factory() as db:
        db.add(_pending_record(
            event_id="evt-cas",
            status="in_flight",
            claim_token="winner-token",
            claimed_at=datetime.now(timezone.utc),
        ))
        await db.commit()

    # Попытка проигравшего (протухший токен) — отброшена.
    async with db_session_factory() as db:
        applied = await webhook_sender._finalize(db, 1, "loser-token", {
            "status": "sent", "claim_token": None, "claimed_at": None,
        })
        await db.commit()
    assert applied is False

    # Попытка владельца — применяется.
    async with db_session_factory() as db:
        applied = await webhook_sender._finalize(db, 1, "winner-token", {
            "status": "sent", "claim_token": None, "claimed_at": None,
        })
        await db.commit()
    assert applied is True

    async with db_session_factory() as db:
        rec = (await db.execute(
            select(WebhookOutbox).where(WebhookOutbox.event_id == "evt-cas")
        )).scalar_one()
        assert rec.status == "sent"
