"""PR-C — GET /health/outbox lag metrics endpoint."""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from uk_management_bot.api.main import outbox_health, settings as main_settings
from uk_management_bot.database.models.webhook_outbox import WebhookOutbox


def _pending(**kw):
    base = dict(
        event_id=str(uuid.uuid4()),
        event="building.created",
        endpoint="/api/webhooks/uk/building",
        payload={"event": "building.created"},
        status="pending",
    )
    base.update(kw)
    return WebhookOutbox(**base)


@pytest.mark.asyncio
async def test_outbox_health_disabled(monkeypatch):
    """Webhook disabled → flat zeroed payload, enabled=False."""
    monkeypatch.setattr(main_settings, "INFRASAFE_WEBHOOK_ENABLED", False)
    result = await outbox_health()
    assert result == {
        "enabled": False,
        "pending": 0,
        "oldest_pending_age_sec": 0,
        "failed_last_24h": 0,
    }


@pytest.mark.asyncio
async def test_outbox_health_db_unavailable(monkeypatch):
    """Enabled but AsyncSessionLocal is None (SQLite mode) → db_unavailable."""
    monkeypatch.setattr(main_settings, "INFRASAFE_WEBHOOK_ENABLED", True)
    monkeypatch.setattr("uk_management_bot.database.session.AsyncSessionLocal", None)
    result = await outbox_health()
    assert result == {"enabled": True, "error": "db_unavailable"}


@pytest.mark.asyncio
async def test_outbox_health_reports_pending(monkeypatch, db_session_factory):
    """Pending records → pending count and a non-negative oldest age."""
    monkeypatch.setattr(main_settings, "INFRASAFE_WEBHOOK_ENABLED", True)
    monkeypatch.setattr(
        "uk_management_bot.database.session.AsyncSessionLocal", db_session_factory
    )
    async with db_session_factory() as db:
        db.add_all([_pending(), _pending(), _pending()])
        await db.commit()

    result = await outbox_health()
    assert result["enabled"] is True
    assert result["pending"] == 3
    assert result["oldest_pending_age_sec"] >= 0
    assert result["failed_last_24h"] == 0


@pytest.mark.asyncio
async def test_outbox_health_reports_failed_24h(monkeypatch, db_session_factory):
    """Recently failed records are counted in failed_last_24h."""
    monkeypatch.setattr(main_settings, "INFRASAFE_WEBHOOK_ENABLED", True)
    monkeypatch.setattr(
        "uk_management_bot.database.session.AsyncSessionLocal", db_session_factory
    )
    async with db_session_factory() as db:
        db.add_all([_pending(status="failed"), _pending(status="failed")])
        await db.commit()

    result = await outbox_health()
    assert result["enabled"] is True
    assert result["pending"] == 0
    assert result["failed_last_24h"] == 2
