"""ARCH-014 — tests for the address EventBus (services/addresses/events.py).

enqueue_outbox runs against real Postgres (webhook_outbox row). The realtime
path is exercised with stubbed Redis routing — no broker required.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.webhook_outbox import WebhookOutbox
from uk_management_bot.services.addresses import events
from uk_management_bot.services import redis_pubsub

pytestmark = pytest.mark.asyncio


_BUILDING_DATA = {
    "id": 999_001, "address": "test-addr", "yard_name": "test-yard",
    "latitude": None, "longitude": None,
}


async def test_enqueue_outbox_writes_row_for_building_event(
    address_async_db, monkeypatch
):
    monkeypatch.setattr(settings, "INFRASAFE_WEBHOOK_ENABLED", True, raising=False)
    await events.enqueue_outbox(
        address_async_db, event="building.created", data=_BUILDING_DATA
    )
    rows = (await address_async_db.execute(
        select(WebhookOutbox).where(WebhookOutbox.event == "building.created")
    )).scalars().all()
    mine = [r for r in rows if r.payload.get("building", {}).get("id") == 999_001]
    assert len(mine) == 1
    assert mine[0].endpoint == "/api/webhooks/uk/building"
    assert mine[0].status == "pending"


async def test_enqueue_outbox_skips_for_yard_event(address_async_db, monkeypatch):
    monkeypatch.setattr(settings, "INFRASAFE_WEBHOOK_ENABLED", True, raising=False)
    before = (await address_async_db.execute(
        select(WebhookOutbox).where(WebhookOutbox.event == "yard.created")
    )).scalars().all()
    await events.enqueue_outbox(
        address_async_db, event="yard.created", data={"id": 1, "name": "y"}
    )
    after = (await address_async_db.execute(
        select(WebhookOutbox).where(WebhookOutbox.event == "yard.created")
    )).scalars().all()
    # yard.* has endpoint=None → no outbox row written.
    assert len(after) == len(before)


async def test_publish_realtime_after_commit_calls_routed_fn(monkeypatch):
    calls = []

    async def _fake(evt, data):
        calls.append((evt, data))

    monkeypatch.setitem(events._ROUTING, "building.updated", ("/x", _fake))
    await events.publish_realtime_after_commit("building.updated", {"id": 7})
    assert calls == [("building.updated", {"id": 7})]


async def test_publish_realtime_skips_when_no_redis_fn(monkeypatch):
    monkeypatch.setitem(events._ROUTING, "building.deleted", (None, None))
    # Must not raise even though there is no redis function to call.
    await events.publish_realtime_after_commit("building.deleted", {"id": 7})


async def test_publish_realtime_redis_failure_does_not_raise(monkeypatch):
    async def _boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(redis_pubsub, "get_pubsub_redis", _boom)
    # publish_building_event swallows the failure; the EventBus must not surface it.
    await events.publish_realtime_after_commit("building.created", _BUILDING_DATA)
