"""Колл-центр (T6, Ф4a-1): Р11 + ``acceptance_mode`` (ремонт из карточки лифта, Р3/Р9)."""
from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.elevator import Elevator
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.elevator_service import generate_public_code
from uk_management_bot.utils.constants import ACCEPTANCE_MODE_MANAGER, ACCEPTANCE_MODE_RESIDENT

URL = "/api/v2/callcenter/requests"


@pytest.fixture(autouse=True)
def _enable_elevators(monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", True)


@pytest_asyncio.fixture
async def elevators(db_session: AsyncSession):
    yard = Yard(name="Двор", is_active=True)
    db_session.add(yard)
    await db_session.flush()
    building = Building(address="ул. Садовая 3", yard_id=yard.id, is_active=True,
                        entrance_count=1, floor_count=9)
    db_session.add(building)
    await db_session.flush()
    ok = Elevator(building_id=building.id, entrance_number=1, elevator_number=1,
                  passport_number="P-1", manufacturer="OTIS", serial_number="S-1",
                  public_code=generate_public_code(), is_commissioned=True,
                  commissioned_at=date(2020, 1, 1), current_status="not_working")
    raw = Elevator(building_id=building.id, entrance_number=1, elevator_number=2,
                   passport_number="P-2", manufacturer="OTIS", serial_number="S-2",
                   public_code=generate_public_code(), is_commissioned=False)
    db_session.add_all([ok, raw])
    await db_session.commit()
    return {"ok": ok, "raw": raw}


def _body(**extra) -> dict:
    body = {"category": "elevator", "urgency": "high", "description": "Звонок: лифт стоит",
            "address": "ул. Садовая 3"}
    body.update(extra)
    return body


async def _row(db_session: AsyncSession, number: str) -> RequestModel:
    return (await db_session.execute(
        select(RequestModel).where(RequestModel.request_number == number)
    )).scalar_one()


@pytest.mark.asyncio
async def test_elevator_category_without_fields_422(client, elevators):
    r = await client.post(URL, json=_body())
    assert r.status_code == 422, r.text
    assert "elevator_id" in r.text


@pytest.mark.asyncio
async def test_elevator_valid_201_default_acceptance_resident(client, db_session, elevators):
    r = await client.post(URL, json=_body(elevator_id=elevators["ok"].id, elevator_operational=False))
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["elevator_id"] == elevators["ok"].id
    assert data["elevator_status"] == "not_working"
    assert "ул. Садовая 3" in data["elevator_label"]
    row = await _row(db_session, data["request_number"])
    assert row.elevator_operational is False
    assert row.acceptance_mode == ACCEPTANCE_MODE_RESIDENT
    assert row.source == "call_center"


@pytest.mark.asyncio
async def test_acceptance_mode_manager_persisted(client, db_session, elevators):
    r = await client.post(URL, json=_body(elevator_id=elevators["ok"].id, elevator_operational=False,
                                         acceptance_mode=ACCEPTANCE_MODE_MANAGER))
    assert r.status_code == 201, r.text
    row = await _row(db_session, r.json()["request_number"])
    assert row.acceptance_mode == ACCEPTANCE_MODE_MANAGER


@pytest.mark.asyncio
async def test_acceptance_mode_invalid_422(client, elevators):
    r = await client.post(URL, json=_body(elevator_id=elevators["ok"].id, elevator_operational=False,
                                         acceptance_mode="robot"))
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_uncommissioned_elevator_422(client, db_session, elevators):
    r = await client.post(URL, json=_body(elevator_id=elevators["raw"].id, elevator_operational=True))
    assert r.status_code == 422, r.text
    assert "не введён" in r.json()["detail"]
    assert (await db_session.execute(select(RequestModel))).scalars().all() == []


@pytest.mark.asyncio
async def test_other_category_with_elevator_201(client, db_session, elevators):
    r = await client.post(URL, json=_body(category="Электрика", elevator_id=elevators["ok"].id,
                                         elevator_operational=True))
    assert r.status_code == 201, r.text
    row = await _row(db_session, r.json()["request_number"])
    assert row.elevator_id == elevators["ok"].id and row.elevator_operational is True


@pytest.mark.asyncio
async def test_flag_off_fields_ignored(client, db_session, elevators, monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    r1 = await client.post(URL, json=_body())
    r2 = await client.post(URL, json=_body(elevator_id=elevators["raw"].id, elevator_operational=True))
    assert r1.status_code == 201 and r2.status_code == 201, (r1.text, r2.text)
    for resp in (r1, r2):
        row = await _row(db_session, resp.json()["request_number"])
        assert row.elevator_id is None and row.elevator_operational is None
