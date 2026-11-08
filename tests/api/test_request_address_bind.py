"""PATCH /api/v2/requests/{n}/address — адрес из справочника к legacy-заявке.

Решение владельца 2026-11-07: заявка без адреса из справочника не уходит в
работу; менеджер привязывает двор/дом/квартиру, исходный текст сохраняется в
примечаниях и аудите. Кейс — 261107-013 «4g 10 etaj» на profk.
"""
import pytest
import pytest_asyncio
from sqlalchemy import select

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.workflow_runner import _new_state_from

URL = "/api/v2/requests/{}/address"


@pytest_asyncio.fixture
async def place(db_session):
    yard = Yard(name="Olmazor City Phase 3", is_active=True)
    db_session.add(yard)
    await db_session.flush()
    building = Building(address="Yangi Olmazor, 4G", yard_id=yard.id, is_active=True,
                        entrance_count=1, floor_count=12)
    dead = Building(address="Снесён", yard_id=yard.id, is_active=False,
                    entrance_count=1, floor_count=1)
    db_session.add_all([building, dead])
    await db_session.commit()
    return {"yard": yard, "building": building, "dead": dead}


async def _fresh(db_session):
    # expire_all() в async-сессии → MissingGreenlet; свежая строка — populate_existing.
    return (await db_session.execute(
        select(RequestModel).where(RequestModel.request_number == "261107-013")
        .execution_options(populate_existing=True))).scalar_one()


async def _request(db_session, owner_id, number="261107-013", **addr):
    fields = {"address": "4g 10 etaj", "address_type": "legacy"} | addr
    req = RequestModel(request_number=number, user_id=owner_id, category="repair",
                       description="kafel qorish kerak", urgency="low", status="Принято",
                       **fields)
    db_session.add(req)
    await db_session.commit()
    return req


@pytest.mark.asyncio
async def test_bind_building_to_legacy_request(client, db_session, manager_user, place):
    await _request(db_session, manager_user.id)
    r = await client.patch(URL.format("261107-013"), json={"building_id": place["building"].id})
    assert r.status_code == 200, r.text
    card = r.json()
    assert card["address_type"] == "building"
    assert card["building_id"] == place["building"].id
    assert card["address"] == "Yangi Olmazor, 4G (Olmazor City Phase 3)"

    row = await _fresh(db_session)
    assert row.notes == "Исходный адрес: 4g 10 etaj"  # этаж из звонка не теряется
    assert _new_state_from(row).address_bound is True
    audit = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "request.address_bound"))).scalar_one()
    assert audit.user_id == manager_user.id
    assert audit.details["old_address"] == "4g 10 etaj"


@pytest.mark.asyncio
async def test_already_bound_409(client, db_session, manager_user, place):
    await _request(db_session, manager_user.id, address="x", address_type="building",
                   building_id=place["building"].id)
    r = await client.patch(URL.format("261107-013"), json={"yard_id": place["yard"].id})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_unknown_request_404(client, place):
    r = await client.patch(URL.format("000000-000"), json={"yard_id": place["yard"].id})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_inactive_building_422_and_nothing_written(client, db_session, manager_user, place):
    await _request(db_session, manager_user.id)
    r = await client.patch(URL.format("261107-013"), json={"building_id": place["dead"].id})
    assert r.status_code == 422
    row = await _fresh(db_session)
    assert row.address_type == "legacy" and _new_state_from(row).address_bound is False


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{}, {"yard_id": 1, "building_id": 1}, {"address": "4g"}])
async def test_body_must_be_one_directory_level(client, body):
    r = await client.patch(URL.format("261107-013"), json=body)
    assert r.status_code == 422
