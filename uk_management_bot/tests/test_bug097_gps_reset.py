"""BUG-097 — bot-side `AddressService.update_building` could not reset GPS to NULL.

The facade built `updates = {k: v ... if v is not None}`, so passing
`gps_latitude=None` (intent: clear the coordinate) was silently dropped and the
old value stuck — InfraSafe never learned the building lost its coordinates.
(The dashboard/API path is already correct: it uses `model_dump(exclude_unset=True)`.)

Fix: GPS args default to a sentinel, so an *explicit* None is forwarded to the
core (which sets NULL + emits building.updated), while omitting the arg leaves
the field unchanged. Other fields keep the `None == don't change` convention.
"""
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest

from uk_management_bot.services import address_service as addr_svc
from uk_management_bot.services.address_service import AddressService


@pytest.fixture
def capture_core_updates(monkeypatch):
    captured = {}

    async def _fake_core_update(adb, building_id, updates):
        captured["updates"] = dict(updates)
        return MagicMock()

    @asynccontextmanager
    async def _fake_session():
        yield MagicMock()

    monkeypatch.setattr(addr_svc._core, "update_building", _fake_core_update)
    monkeypatch.setattr(addr_svc, "_async_session", _fake_session)
    return captured


@pytest.mark.asyncio
async def test_explicit_none_gps_is_forwarded_as_reset(capture_core_updates):
    await AddressService.update_building(
        session=MagicMock(), building_id=1, gps_latitude=None, gps_longitude=None
    )
    updates = capture_core_updates["updates"]
    assert "gps_latitude" in updates and updates["gps_latitude"] is None
    assert "gps_longitude" in updates and updates["gps_longitude"] is None


@pytest.mark.asyncio
async def test_omitted_gps_is_left_unchanged(capture_core_updates):
    await AddressService.update_building(
        session=MagicMock(), building_id=1, address="ул. Новая, 5"
    )
    updates = capture_core_updates["updates"]
    assert "gps_latitude" not in updates
    assert "gps_longitude" not in updates
    assert updates["address"] == "ул. Новая, 5"


@pytest.mark.asyncio
async def test_explicit_gps_values_still_set(capture_core_updates):
    await AddressService.update_building(
        session=MagicMock(), building_id=1, gps_latitude=41.3, gps_longitude=69.2
    )
    updates = capture_core_updates["updates"]
    assert updates["gps_latitude"] == 41.3
    assert updates["gps_longitude"] == 69.2
