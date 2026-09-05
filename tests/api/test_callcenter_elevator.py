"""Колл-центр (T6, Ф4a-1): Р11 + ``acceptance_mode`` (ремонт из карточки лифта, Р3/Р9).

Дом заявки выводится из квартиры жителя (``user_id`` + ``apartment_id``): лифт
обязан принадлежать этому дому; при свободном legacy-адресе дома нет → 422.
"""
from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.elevator import Elevator
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
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
    other = Building(address="ул. Чужая 9", yard_id=yard.id, is_active=True,
                     entrance_count=1, floor_count=5)
    db_session.add_all([building, other])
    await db_session.flush()
    apt = Apartment(building_id=building.id, apartment_number="4", is_active=True)
    resident = User(telegram_id=4242, username="res", first_name="R", roles='["applicant"]',
                    status="approved", phone="+998", language="ru")
    db_session.add_all([apt, resident])
    await db_session.flush()
    db_session.add(UserApartment(user_id=resident.id, apartment_id=apt.id, status="approved"))
    ok = Elevator(building_id=building.id, entrance_number=1, elevator_number=1,
                  passport_number="P-1", manufacturer="OTIS", serial_number="S-1",
                  public_code=generate_public_code(), is_commissioned=True,
                  commissioned_at=date(2020, 1, 1), current_status="not_working")
    raw = Elevator(building_id=building.id, entrance_number=1, elevator_number=2,
                   passport_number="P-2", manufacturer="OTIS", serial_number="S-2",
                   public_code=generate_public_code(), is_commissioned=False)
    foreign = Elevator(building_id=other.id, entrance_number=1, elevator_number=1,
                       passport_number="P-9", manufacturer="OTIS", serial_number="S-9",
                       public_code=generate_public_code(), is_commissioned=True,
                       commissioned_at=date(2020, 1, 1), current_status="working")
    db_session.add_all([ok, raw, foreign])
    await db_session.commit()
    return {"ok": ok, "raw": raw, "foreign": foreign, "resident": resident, "apt": apt}


def _body(elevators=None, **extra) -> dict:
    """Тело с квартирой жителя (дом известен); без ``elevators`` — legacy-адрес."""
    body = {"category": "elevator", "urgency": "high", "description": "Звонок: лифт стоит"}
    if elevators is None:
        body["address"] = "ул. Садовая 3"
    else:
        body["user_id"] = elevators["resident"].id
        body["apartment_id"] = elevators["apt"].id
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
    r = await client.post(URL, json=_body(elevators, elevator_id=elevators["ok"].id,
                                         elevator_operational=False))
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
    r = await client.post(URL, json=_body(elevators, elevator_id=elevators["ok"].id,
                                         elevator_operational=False,
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
    r = await client.post(URL, json=_body(elevators, elevator_id=elevators["raw"].id,
                                         elevator_operational=True))
    assert r.status_code == 422, r.text
    assert "не введён" in r.json()["detail"]
    assert (await db_session.execute(select(RequestModel))).scalars().all() == []


@pytest.mark.asyncio
async def test_other_category_with_elevator_201(client, db_session, elevators):
    r = await client.post(URL, json=_body(elevators, category="Электрика",
                                         elevator_id=elevators["ok"].id, elevator_operational=True))
    assert r.status_code == 201, r.text
    row = await _row(db_session, r.json()["request_number"])
    assert row.elevator_id == elevators["ok"].id and row.elevator_operational is True


@pytest.mark.asyncio
async def test_elevator_of_other_building_422(client, db_session, elevators):
    """Security T6: лифт чужого дома к квартире жителя не привязать."""
    r = await client.post(URL, json=_body(elevators, elevator_id=elevators["foreign"].id,
                                         elevator_operational=False))
    assert r.status_code == 422, r.text
    assert "другому дому" in r.json()["detail"]
    assert (await db_session.execute(select(RequestModel))).scalars().all() == []


@pytest.mark.asyncio
async def test_legacy_address_without_building_422(client, db_session, elevators):
    """Свободный адрес без квартиры — дома нет → лифт привязать нельзя."""
    r = await client.post(URL, json=_body(elevator_id=elevators["ok"].id, elevator_operational=False))
    assert r.status_code == 422, r.text
    assert "нужен дом или квартира" in r.json()["detail"]
    assert (await db_session.execute(select(RequestModel))).scalars().all() == []


@pytest.mark.asyncio
async def test_flag_off_fields_ignored(client, db_session, elevators, monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    r1 = await client.post(URL, json=_body())
    r2 = await client.post(URL, json=_body(elevator_id=elevators["raw"].id, elevator_operational=True))
    assert r1.status_code == 201 and r2.status_code == 201, (r1.text, r2.text)
    for resp in (r1, r2):
        row = await _row(db_session, resp.json()["request_number"])
        assert row.elevator_id is None and row.elevator_operational is None
