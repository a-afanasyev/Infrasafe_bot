"""ARCH-014 — unit tests for services/addresses/core.py.

Postgres-only (see conftest.address_async_db). Redis publishing is stubbed so
tests do not need a running Redis; the webhook outbox path runs for real so we
can assert the row shape.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models import Building, User
from uk_management_bot.database.models.webhook_outbox import WebhookOutbox
from uk_management_bot.services.addresses import core
from uk_management_bot.services.addresses.exceptions import (
    AddressNotFound, AddressConflict,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _stub_realtime_and_enable_webhooks(monkeypatch):
    """Skip Redis (no running broker needed) and force webhook outbox writes."""
    async def _noop(event, data):  # noqa: ANN001
        return None
    monkeypatch.setattr(core, "publish_realtime_after_commit", _noop)
    monkeypatch.setattr(settings, "INFRASAFE_WEBHOOK_ENABLED", True, raising=False)


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


@pytest_asyncio.fixture
async def uid(address_async_db) -> int:
    """Create a throwaway user and return its id (FK target for created_by etc.)."""
    user = User(telegram_id=int(uuid.uuid4().int % 10**15))
    address_async_db.add(user)
    await address_async_db.flush()
    return user.id


@pytest_asyncio.fixture
async def yard(address_async_db, uid):
    return await core.create_yard(
        address_async_db, name=f"yard-{_suffix()}", created_by=uid
    )


@pytest_asyncio.fixture
async def building(address_async_db, yard, uid):
    return await core.create_building(
        address_async_db, address=f"bld-{_suffix()}", yard_id=yard.id, created_by=uid
    )


# ───────────────────────── Yards ─────────────────────────

async def test_create_yard(address_async_db, uid):
    yard = await core.create_yard(
        address_async_db, name=f"yard-{_suffix()}", created_by=uid,
        gps_latitude=41.1, gps_longitude=69.2,
    )
    assert yard.id is not None
    assert yard.is_active is True


async def test_create_yard_duplicate_name_conflicts(address_async_db, yard, uid):
    with pytest.raises(AddressConflict):
        await core.create_yard(address_async_db, name=yard.name, created_by=uid)


async def test_update_yard_not_found(address_async_db):
    with pytest.raises(AddressNotFound):
        await core.update_yard(address_async_db, 10**9, {"description": "x"})


async def test_update_yard_blocks_deactivation_with_active_buildings(
    address_async_db, yard, building
):
    with pytest.raises(AddressConflict):
        await core.update_yard(address_async_db, yard.id, {"is_active": False})


async def test_update_yard_deactivates_when_empty(address_async_db, yard):
    updated = await core.update_yard(address_async_db, yard.id, {"is_active": False})
    assert updated.is_active is False


async def test_delete_yard_blocks_with_active_buildings(
    address_async_db, yard, building
):
    with pytest.raises(AddressConflict):
        await core.delete_yard(address_async_db, yard.id)


# ───────────────────────── Buildings ─────────────────────────

async def test_create_building(address_async_db, yard, uid):
    bld = await core.create_building(
        address_async_db, address=f"bld-{_suffix()}", yard_id=yard.id, created_by=uid
    )
    assert bld.id is not None
    assert bld.yard_id == yard.id


async def test_create_building_unknown_yard(address_async_db, uid):
    with pytest.raises(AddressNotFound):
        await core.create_building(
            address_async_db, address="bld-x", yard_id=10**9, created_by=uid
        )


async def test_create_building_inactive_yard(address_async_db, yard, uid):
    await core.update_yard(address_async_db, yard.id, {"is_active": False})
    with pytest.raises(AddressConflict):
        await core.create_building(
            address_async_db, address="bld-x", yard_id=yard.id, created_by=uid
        )


async def test_create_building_writes_one_webhook_outbox_row(
    address_async_db, yard, uid
):
    bld = await core.create_building(
        address_async_db, address=f"bld-{_suffix()}", yard_id=yard.id, created_by=uid
    )
    rows = (await address_async_db.execute(
        select(WebhookOutbox).where(WebhookOutbox.event == "building.created")
    )).scalars().all()
    mine = [r for r in rows if r.payload.get("building", {}).get("id") == bld.id]
    assert len(mine) == 1
    payload = mine[0].payload
    # Envelope built exactly once: event_id at top level, building nested once.
    assert "event_id" in payload and "building" in payload
    assert "event_id" not in payload["building"]
    assert payload["building"]["town"] == yard.name


async def test_update_building_blocks_deactivation_with_active_apartments(
    address_async_db, building, uid
):
    await core.create_apartment(
        address_async_db, building_id=building.id,
        apartment_number=f"a{_suffix()}", created_by=uid,
    )
    with pytest.raises(AddressConflict):
        await core.update_building(address_async_db, building.id, {"is_active": False})


async def test_update_building_yard_id_change_validates_target(
    address_async_db, building
):
    with pytest.raises(AddressNotFound):
        await core.update_building(address_async_db, building.id, {"yard_id": 10**9})


async def test_delete_building(address_async_db, building):
    await core.delete_building(address_async_db, building.id)
    refreshed = await address_async_db.get(Building, building.id)
    assert refreshed.is_active is False


# ───────── ARCH-010: change-gate / delete-no-op / building_version ─────────

async def _outbox_rows_for(db, event: str, building_id: int) -> list[WebhookOutbox]:
    rows = (await db.execute(
        select(WebhookOutbox).where(WebhookOutbox.event == event)
    )).scalars().all()
    return [r for r in rows if r.payload.get("building", {}).get("id") == building_id]


async def test_update_building_same_values_no_bump_no_emit(
    address_async_db, building, monkeypatch
):
    """PATCH теми же значениями — no-op: без bump версии, emit и Redis-publish."""
    published = []

    async def _spy(event, data):  # noqa: ANN001
        published.append(event)

    monkeypatch.setattr(core, "publish_realtime_after_commit", _spy)
    updated = await core.update_building(
        address_async_db, building.id,
        {"address": building.address, "yard_id": building.yard_id},
    )
    assert updated.building_version == 0
    assert await _outbox_rows_for(address_async_db, "building.updated", building.id) == []
    assert published == []


async def test_update_building_real_change_bumps_and_emits(
    address_async_db, building, monkeypatch
):
    published = []

    async def _spy(event, data):  # noqa: ANN001
        published.append(event)

    monkeypatch.setattr(core, "publish_realtime_after_commit", _spy)
    updated = await core.update_building(
        address_async_db, building.id, {"address": f"bld-{_suffix()}"}
    )
    assert updated.building_version == 1
    assert len(await _outbox_rows_for(address_async_db, "building.updated", building.id)) == 1
    assert published == ["building.updated"]


async def test_delete_building_already_inactive_is_noop(address_async_db, building):
    await core.delete_building(address_async_db, building.id)
    assert len(await _outbox_rows_for(address_async_db, "building.deleted", building.id)) == 1
    # Повторный delete уже-неактивного — no-op: без второй строки и bump'а.
    await core.delete_building(address_async_db, building.id)
    refreshed = await address_async_db.get(Building, building.id)
    assert refreshed.building_version == 1
    assert len(await _outbox_rows_for(address_async_db, "building.deleted", building.id)) == 1


async def test_delete_reactivate_delete_two_distinct_deletes(address_async_db, building):
    """Цикл delete→reactivate→delete: два реальных удаления с разными версиями."""
    await core.delete_building(address_async_db, building.id)
    await core.update_building(address_async_db, building.id, {"is_active": True})
    await core.delete_building(address_async_db, building.id)
    refreshed = await address_async_db.get(Building, building.id)
    assert refreshed.building_version == 3
    deletes = await _outbox_rows_for(address_async_db, "building.deleted", building.id)
    assert len(deletes) == 2
    assert len({d.event_id for d in deletes}) == 2  # версии дают разные id


# ───────────────────────── Apartments ─────────────────────────

async def test_create_apartment(address_async_db, building, uid):
    apt = await core.create_apartment(
        address_async_db, building_id=building.id,
        apartment_number=f"a{_suffix()}", created_by=uid,
    )
    assert apt.id is not None


async def test_create_apartment_duplicate_number_conflicts(
    address_async_db, building, uid
):
    number = f"a{_suffix()}"
    await core.create_apartment(
        address_async_db, building_id=building.id,
        apartment_number=number, created_by=uid,
    )
    with pytest.raises(AddressConflict):
        await core.create_apartment(
            address_async_db, building_id=building.id,
            apartment_number=number, created_by=uid,
        )


async def test_bulk_create_rejects_empty_and_oversized(address_async_db, building, uid):
    created, skipped, errors = await core.bulk_create_apartments(
        address_async_db, building_id=building.id, created_by=uid,
        apartment_numbers=[f"ok{_suffix()}", "  ", "x" * 25],
    )
    assert created == 1
    assert len(errors) == 2


async def test_bulk_create_skips_existing(address_async_db, building, uid):
    number = f"a{_suffix()}"
    await core.create_apartment(
        address_async_db, building_id=building.id,
        apartment_number=number, created_by=uid,
    )
    created, skipped, errors = await core.bulk_create_apartments(
        address_async_db, building_id=building.id, created_by=uid,
        apartment_numbers=[number, f"new{_suffix()}"],
    )
    assert created == 1 and skipped == 1


async def test_delete_apartment_blocked_by_approved_resident(
    address_async_db, building, uid
):
    apt = await core.create_apartment(
        address_async_db, building_id=building.id,
        apartment_number=f"a{_suffix()}", created_by=uid,
    )
    ua = await core.request_apartment(
        address_async_db, user_id=uid, apartment_id=apt.id
    )
    await core.approve_apartment_request(
        address_async_db, user_apartment_id=ua.id, reviewer_id=uid
    )
    with pytest.raises(AddressConflict):
        await core.delete_apartment(address_async_db, apt.id)


# ─────────────────── User ↔ Apartment requests ───────────────────

async def test_request_apartment_then_approve(address_async_db, building, uid):
    apt = await core.create_apartment(
        address_async_db, building_id=building.id,
        apartment_number=f"a{_suffix()}", created_by=uid,
    )
    ua = await core.request_apartment(address_async_db, user_id=uid, apartment_id=apt.id)
    assert ua.status == "pending"
    approved = await core.approve_apartment_request(
        address_async_db, user_apartment_id=ua.id, reviewer_id=uid
    )
    assert approved.status == "approved"


async def test_request_apartment_duplicate_pending_conflicts(
    address_async_db, building, uid
):
    apt = await core.create_apartment(
        address_async_db, building_id=building.id,
        apartment_number=f"a{_suffix()}", created_by=uid,
    )
    await core.request_apartment(address_async_db, user_id=uid, apartment_id=apt.id)
    with pytest.raises(AddressConflict):
        await core.request_apartment(address_async_db, user_id=uid, apartment_id=apt.id)


async def test_approve_already_processed_conflicts(address_async_db, building, uid):
    apt = await core.create_apartment(
        address_async_db, building_id=building.id,
        apartment_number=f"a{_suffix()}", created_by=uid,
    )
    ua = await core.request_apartment(address_async_db, user_id=uid, apartment_id=apt.id)
    await core.approve_apartment_request(
        address_async_db, user_apartment_id=ua.id, reviewer_id=uid
    )
    with pytest.raises(AddressConflict):
        await core.reject_apartment_request(
            address_async_db, user_apartment_id=ua.id, reviewer_id=uid, comment="late"
        )
