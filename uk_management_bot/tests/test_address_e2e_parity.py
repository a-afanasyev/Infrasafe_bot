"""ARCH-014 — parity tests: the bot adapter and the API path produce identical
effects, because both delegate to services/addresses/core.

The API endpoint is a thin wrapper over `core.*`, so the "API path" here calls
`core` directly. The bot path goes through AddressService; its private
`_async_session()` is patched to hand back the isolated test session.
"""
from __future__ import annotations

import contextlib
import uuid

import pytest
import pytest_asyncio

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models import User
from uk_management_bot.services import address_service
from uk_management_bot.services.address_service import AddressService
from uk_management_bot.services.addresses import core
from uk_management_bot.services.addresses.exceptions import AddressConflict

pytestmark = pytest.mark.asyncio


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


def _strip_volatile(payload: dict) -> dict:
    """Drop fields that legitimately differ between two emissions."""
    out = {k: v for k, v in payload.items() if k not in ("event_id", "timestamp")}
    return out


@pytest.fixture(autouse=True)
def _bot_uses_test_session(address_async_db, monkeypatch):
    """Route AddressService's AsyncSession to the isolated test session, and
    stub Redis / enable the webhook outbox."""
    @contextlib.asynccontextmanager
    async def _proxy():
        yield address_async_db

    monkeypatch.setattr(address_service, "_async_session", _proxy)

    async def _noop(event, data):  # noqa: ANN001
        return None
    monkeypatch.setattr(core, "publish_realtime_after_commit", _noop)
    monkeypatch.setattr(settings, "INFRASAFE_WEBHOOK_ENABLED", True, raising=False)


@pytest_asyncio.fixture
async def uid(address_async_db) -> int:
    user = User(telegram_id=int(uuid.uuid4().int % 10**15))
    address_async_db.add(user)
    await address_async_db.flush()
    return user.id


@pytest_asyncio.fixture
async def yard(address_async_db, uid):
    return await core.create_yard(
        address_async_db, name=f"yard-{_suffix()}", created_by=uid
    )


async def test_bot_create_building_identical_outbox_to_api(
    address_async_db, yard, uid
):
    from sqlalchemy import select
    from uk_management_bot.database.models.webhook_outbox import WebhookOutbox

    # Bot path
    bot_building, bot_err = await AddressService.create_building(
        session=None, address=f"bld-bot-{_suffix()}", yard_id=yard.id, created_by=uid
    )
    assert bot_err is None and bot_building is not None

    # API path (router delegates straight to core)
    api_building = await core.create_building(
        address_async_db, address=f"bld-api-{_suffix()}",
        yard_id=yard.id, created_by=uid,
    )

    rows = (await address_async_db.execute(
        select(WebhookOutbox).where(WebhookOutbox.event == "building.created")
    )).scalars().all()
    by_id = {r.payload["building"]["id"]: r.payload for r in rows}
    bot_payload = by_id[bot_building.id]
    api_payload = by_id[api_building.id]

    # Same envelope shape and same field set; only the building id/address and
    # the volatile event_id/timestamp differ.
    assert _strip_volatile(bot_payload).keys() == _strip_volatile(api_payload).keys()
    assert bot_payload["event"] == api_payload["event"] == "building.created"
    assert bot_payload["building"].keys() == api_payload["building"].keys()
    assert bot_payload["building"]["town"] == api_payload["building"]["town"] == yard.name


async def test_bot_update_yard_deactivation_blocked_like_api(
    address_async_db, yard, uid
):
    await core.create_building(
        address_async_db, address=f"bld-{_suffix()}", yard_id=yard.id, created_by=uid
    )

    # API path: core raises AddressConflict.
    with pytest.raises(AddressConflict):
        await core.update_yard(address_async_db, yard.id, {"is_active": False})

    # Bot path: adapter swallows the same domain error into the (None, error) tuple.
    result, error = await AddressService.update_yard(
        session=None, yard_id=yard.id, is_active=False
    )
    assert result is None
    assert error  # non-empty Russian-language message
