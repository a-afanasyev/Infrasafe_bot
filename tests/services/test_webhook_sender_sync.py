"""PR-E — queue_webhook_sync (sync-Session variant of queue_webhook).

Uses a self-contained in-memory SQLite sync session that creates only the
webhook_outbox table — no dependency on the larger schema or on
SessionLocal's configured DATABASE_URL.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from uk_management_bot.database.models.webhook_outbox import WebhookOutbox
from uk_management_bot.services.webhook_sender import EventIdentity, queue_webhook_sync


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
    # ARCH-010: versioned-событие требует identity (fail-loud в funnel'е).
    queue_webhook_sync(
        sync_session,
        "building.updated",
        "/api/webhooks/uk/building",
        {"id": 2, "address": "B", "yard_name": "Y2"},
        EventIdentity(version=1),
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


# ===== PR-F: latitude / longitude pass-through =====

def test_build_building_payload_includes_coordinates():
    """Latitude and longitude land in payload.building unchanged."""
    from uk_management_bot.services.webhook_sender import build_building_payload

    result = build_building_payload("building.created", {
        "id": 42, "address": "ul. Navoi 1", "yard_name": "Y1",
        "latitude": 41.123456, "longitude": 69.654321,
    })
    assert result["building"]["latitude"] == 41.123456
    assert result["building"]["longitude"] == 69.654321


def test_build_building_payload_missing_coords_returns_none():
    """No coords in data → payload carries null coords (backward-compat)."""
    from uk_management_bot.services.webhook_sender import build_building_payload

    result = build_building_payload("building.created", {
        "id": 42, "address": "x", "yard_name": "y",
    })
    assert result["building"]["latitude"] is None
    assert result["building"]["longitude"] is None


def test_queue_webhook_sync_propagates_coords_to_outbox(sync_session, webhook_enabled):
    """End-to-end: coords in data dict survive into the stored outbox payload."""
    queue_webhook_sync(
        sync_session,
        "building.created",
        "/api/webhooks/uk/building",
        {
            "id": 1, "address": "A", "yard_name": "Y",
            "latitude": 41.111, "longitude": 69.222,
        },
    )
    sync_session.commit()

    row = sync_session.query(WebhookOutbox).first()
    assert row.payload["building"]["latitude"] == 41.111
    assert row.payload["building"]["longitude"] == 69.222


# ===== PR6 (SSOT cluster #1): async/sync parity via shared outbox builder =====

import uk_management_bot.services.webhook_sender as ws  # noqa: E402
from uk_management_bot.services.webhook_sender import queue_webhook  # noqa: E402


def _normalize(record: WebhookOutbox) -> dict:
    """Record fields + payload без недетерминированных event_id/timestamp."""
    payload = dict(record.payload)
    payload.pop("event_id", None)
    payload.pop("timestamp", None)
    return {
        "event": record.event,
        "endpoint": record.endpoint,
        "status": record.status,
        "payload": payload,
        "event_id_matches_payload": record.event_id == record.payload["event_id"],
    }


async def _capture_async_record(event, endpoint, data, identity=None) -> WebhookOutbox:
    """ARCH-010: queue_webhook пишет через execute(INSERT ... ON CONFLICT), а не
    db.add — MagicMock-перехват больше невозможен; поднимаем реальную aiosqlite
    сессию и читаем строку из БД."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import (
        AsyncSession, async_sessionmaker, create_async_engine,
    )
    engine = create_async_engine("sqlite+aiosqlite://")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: WebhookOutbox.__table__.create(sync_conn)
            )
        AF = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with AF() as db:
            await queue_webhook(db, event, endpoint, data, identity)
            await db.commit()
            row = (await db.execute(select(WebhookOutbox))).scalars().one()
            db.expunge(row)
            return row
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event,endpoint,data,identity",
    [
        ("building.created", "/api/webhooks/uk/building",
         {"id": 1, "address": "A", "yard_name": "Y"}, None),
        # ARCH-010: versioned-событие требует identity (fail-loud в funnel'е).
        ("request.status_changed", "/api/webhooks/uk/request",
         {"request_number": "260610-001", "old_status": "В работе",
          "new_status": "Выполнена"}, EventIdentity(version=1)),
        # generic-ветка (не building.*/request.*)
        ("shift.opened", "/api/webhooks/uk/shift", {"shift_id": 7}, None),
    ],
)
async def test_async_sync_outbox_parity(sync_session, webhook_enabled,
                                        event, endpoint, data, identity):
    """queue_webhook и queue_webhook_sync строят ИДЕНТИЧНЫЕ outbox-записи.

    Раньше builder был скопирован в обе функции с комментарием «keep in
    sync» — этот тест ловит расхождение, если копии разъедутся (а после
    PR6 закрепляет общий _build_outbox_record).
    """
    async_record = await _capture_async_record(event, endpoint, data, identity)

    queue_webhook_sync(sync_session, event, endpoint, data, identity)
    sync_record = sync_session.query(WebhookOutbox).first() or \
        [o for o in sync_session.new if isinstance(o, WebhookOutbox)][0]

    assert _normalize(async_record) == _normalize(sync_record)


def test_both_queue_functions_use_shared_builder():
    """PR6: обе queue_webhook* должны звать единый _build_outbox_record
    (никаких скопированных builder'ов с 'keep in sync')."""
    import inspect

    assert hasattr(ws, "_build_outbox_record"), \
        "shared _build_outbox_record helper must exist (PR6)"
    for fn in (ws.queue_webhook, ws.queue_webhook_sync):
        assert "_build_outbox_record" in inspect.getsource(fn), \
            f"{fn.__name__} must delegate to _build_outbox_record"


# ===== ARCH-010: ON CONFLICT DO NOTHING — локальный дедуп дубль-emit =====

def test_double_enqueue_same_identity_single_row(sync_session, webhook_enabled):
    """Два enqueue одного логического события (тот же детерминированный
    event_id) → в outbox ровно одна строка, без IntegrityError."""
    for _ in range(2):
        queue_webhook_sync(
            sync_session,
            "building.updated",
            "/api/webhooks/uk/building",
            {"id": 3, "address": "C", "yard_name": "Y"},
            EventIdentity(version=5),
        )
    sync_session.commit()
    assert sync_session.query(WebhookOutbox).count() == 1


def test_double_enqueue_different_versions_two_rows(sync_session, webhook_enabled):
    """Разные версии = разные события — дедуп НЕ должен их глушить."""
    for v in (1, 2):
        queue_webhook_sync(
            sync_session,
            "building.updated",
            "/api/webhooks/uk/building",
            {"id": 3, "address": "C", "yard_name": "Y"},
            EventIdentity(version=v),
        )
    sync_session.commit()
    assert sync_session.query(WebhookOutbox).count() == 2


# ===== ARCH-010: Redis-инвариант — identity не утекает в shared data =====

def test_building_event_data_stays_json_scalar():
    """build_building_event_data (shared с Redis publish_building_event) обязан
    возвращать только JSON-скаляры: версия/identity/datetime в data не попадают —
    bare json.dumps в redis_pubsub тихо сломал бы фронт-путь."""
    from types import SimpleNamespace

    from uk_management_bot.services.addresses.payloads import build_building_event_data

    building = SimpleNamespace(
        id=1, address="A", gps_latitude=41.1, gps_longitude=69.2,
        yard_id=2, entrance_count=3, floor_count=9, is_active=True,
        building_version=7,  # ARCH-010: версия есть на модели, но НЕ в data
    )
    data = build_building_event_data(building, yard_name="Y")

    assert "building_version" not in data
    assert "version" not in data
    allowed = (str, int, float, bool, type(None))
    for key, value in data.items():
        assert isinstance(value, allowed), f"{key}={value!r} не JSON-скаляр"
