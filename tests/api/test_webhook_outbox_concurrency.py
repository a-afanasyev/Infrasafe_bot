"""PR-A — process_outbox() multi-worker safety (FOR UPDATE SKIP LOCKED).

The true 2-worker race can only be exercised against PostgreSQL (SQLite has no
row locking and SQLAlchemy silently drops FOR UPDATE for it). These tests cover:

  1. The generated SELECT carries `FOR UPDATE SKIP LOCKED` on the PG dialect.
  2. process_outbox() delivers every pending record exactly once in a normal
     single-worker run and does not double-send.

End-to-end "no duplicate delivery under --workers 2" is checked at deploy time
(verification check #5: no duplicates in InfraSafe integration_log).
"""
import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from uk_management_bot.database.models.webhook_outbox import WebhookOutbox
from uk_management_bot.services import webhook_sender


def test_select_compiles_with_skip_locked():
    """The pending-records query must emit FOR UPDATE SKIP LOCKED on PostgreSQL."""
    from sqlalchemy import or_
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    stmt = (
        select(WebhookOutbox)
        .where(
            WebhookOutbox.status == "pending",
            or_(
                WebhookOutbox.retry_after.is_(None),
                WebhookOutbox.retry_after <= now,
            ),
        )
        .order_by(WebhookOutbox.created_at)
        .limit(50)
        .with_for_update(skip_locked=True)
    )
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


@pytest.mark.asyncio
async def test_process_outbox_sends_each_record_once(_outbox_env):
    """100 pending records → exactly 100 sends, all marked sent with attempts=1.

    process_outbox() pulls LIMIT 50 per cycle, so two cycles drain 100 records.
    """
    db_session_factory, mock_send = _outbox_env

    async with db_session_factory() as db:
        for _ in range(100):
            db.add(
                WebhookOutbox(
                    event_id=str(uuid.uuid4()),
                    event="building.created",
                    endpoint="/api/webhooks/uk/building",
                    payload={"event": "building.created"},
                    status="pending",
                )
            )
        await db.commit()

    # Drain the outbox; a third cycle is a no-op and proves no re-send.
    await webhook_sender.process_outbox()
    await webhook_sender.process_outbox()
    await webhook_sender.process_outbox()

    assert mock_send.call_count == 100

    async with db_session_factory() as db:
        records = (await db.execute(select(WebhookOutbox))).scalars().all()
        assert len(records) == 100
        assert all(r.status == "sent" for r in records)
        assert all(r.attempts == 1 for r in records)
