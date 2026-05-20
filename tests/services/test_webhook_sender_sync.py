"""PR-E — queue_webhook_sync (sync-Session variant of queue_webhook).

Uses a self-contained in-memory SQLite sync session that creates only the
webhook_outbox table — no dependency on the larger schema or on
SessionLocal's configured DATABASE_URL.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.webhook_outbox import WebhookOutbox
from uk_management_bot.services.webhook_sender import queue_webhook_sync


@pytest.fixture
def sync_session():
    """Fresh in-memory sync Session with the webhook_outbox table only."""
    engine = create_engine("sqlite:///:memory:")
    WebhookOutbox.__table__.create(engine)
    SessionFactory = sessionmaker(bind=engine)
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def webhook_enabled(monkeypatch):
    """Default: webhook enabled. Tests opting out override via monkeypatch."""
    monkeypatch.setattr(
        "uk_management_bot.config.settings.settings.INFRASAFE_WEBHOOK_ENABLED",
        True,
    )


def test_queue_webhook_sync_disabled_skips(monkeypatch, sync_session):
    """ENABLED=False → no outbox row, WARNING logged (caller handles via reconcile)."""
    monkeypatch.setattr(
        "uk_management_bot.config.settings.settings.INFRASAFE_WEBHOOK_ENABLED",
        False,
    )

    queue_webhook_sync(
        sync_session,
        "building.created",
        "/api/webhooks/uk/building",
        {"id": 1, "address": "A", "yard_name": "Y"},
    )
    sync_session.commit()

    assert sync_session.query(WebhookOutbox).count() == 0


def test_queue_webhook_sync_creates_pending_row(sync_session, webhook_enabled):
    """A building.created event lands as a pending outbox row with canonical payload."""
    queue_webhook_sync(
        sync_session,
        "building.created",
        "/api/webhooks/uk/building",
        {"id": 1, "address": "A", "yard_name": "Y"},
    )
    sync_session.commit()

    row = sync_session.query(WebhookOutbox).first()
    assert row is not None
    assert row.event == "building.created"
    assert row.status == "pending"
    assert row.endpoint == "/api/webhooks/uk/building"
    assert row.payload["building"]["id"] == 1
    assert row.payload["building"]["address"] == "A"
    assert row.payload["building"]["town"] == "Y"


def test_queue_webhook_sync_uses_building_payload_builder(sync_session, webhook_enabled):
    """building.updated also routes through build_building_payload."""
    queue_webhook_sync(
        sync_session,
        "building.updated",
        "/api/webhooks/uk/building",
        {"id": 2, "address": "B", "yard_name": "Y2"},
    )
    sync_session.commit()

    row = sync_session.query(WebhookOutbox).first()
    assert row.payload["event"] == "building.updated"
    assert "event_id" in row.payload
    assert row.payload["building"]["id"] == 2


def test_queue_webhook_sync_uses_request_payload_builder(sync_session, webhook_enabled):
    """request.* events route through build_request_payload."""
    queue_webhook_sync(
        sync_session,
        "request.created",
        "/api/webhooks/uk/request",
        {
            "request_number": "R-1",
            "category": "plumbing",
            "status": "new",
            "urgency": "normal",
        },
    )
    sync_session.commit()

    row = sync_session.query(WebhookOutbox).first()
    assert row.payload["event"] == "request.created"
    assert row.payload["request"]["request_number"] == "R-1"


def test_queue_webhook_sync_does_not_commit(sync_session, webhook_enabled):
    """Caller owns the transaction — rollback must drop the outbox row."""
    queue_webhook_sync(
        sync_session,
        "building.created",
        "/api/webhooks/uk/building",
        {"id": 1, "address": "A", "yard_name": "Y"},
    )
    # Row exists in the open transaction.
    assert sync_session.query(WebhookOutbox).count() == 1

    sync_session.rollback()
    assert sync_session.query(WebhookOutbox).count() == 0
