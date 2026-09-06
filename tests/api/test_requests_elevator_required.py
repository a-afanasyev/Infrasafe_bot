"""Р11 в API-конструкторах заявок (T6, Ф4a-1): TWA + инспектор + карточка.

Заявка категории «лифт» обязана нести ``elevator_id`` и
``elevator_operational`` — и лифт обязан быть пригодным (активен, введён в
эксплуатацию). Флаг ``ELEVATORS_ENABLED`` выключен → поля игнорируются,
поведение прежнее. ``RequestCard`` несёт ``elevator_id``/``elevator_label``/
``elevator_status`` для канбана и детали.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_current_user, get_db
from uk_management_bot.api.main import app
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.elevator import Elevator
from uk_management_bot.database.models.elevators_config import ElevatorsConfig
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services.elevator_service import generate_public_code

URL = "/api/v2/requests"


@pytest.fixture(autouse=True)
def _enable_elevators(monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", True)


@pytest_asyncio.fixture
async def addr_tree(db_session: AsyncSession):
    yard = Yard(name="Двор А", is_active=True)
    db_session.add(yard)
    await db_session.flush()
    building = Building(address="ул. Ленина 1", yard_id=yard.id, is_active=True,
                        entrance_count=2, floor_count=9)
    other = Building(address="ул. Мира 7", yard_id=yard.id, is_active=True,
                     entrance_count=1, floor_count=5)
    db_session.add_all([building, other])
    await db_session.flush()
    apt = Apartment(building_id=building.id, apartment_number="12", is_active=True)
    db_session.add(apt)
    await db_session.commit()
    return {"yard": yard, "building": building, "other": other, "apt": apt}


def _elevator(building_id: int, *, number: int, commissioned: bool = True,
              status: str | None = "working") -> Elevator:
    return Elevator(
        building_id=building_id, entrance_number=1, elevator_number=number,
        passport_number=f"P-{number}", manufacturer="OTIS", serial_number=f"S-{number}",
        public_code=generate_public_code(),
        is_commissioned=commissioned,
        commissioned_at=date(2020, 1, 1) if commissioned else None,
        current_status=status if commissioned else None,
    )


@pytest_asyncio.fixture
async def elevators(db_session: AsyncSession, addr_tree):
    """ok — пригодный лифт дома; raw — не введён; foreign — лифт другого дома;
    repairing/maintained — «В ремонте»/«На ТО» (Р18); broken — «не работает»."""
    ok = _elevator(addr_tree["building"].id, number=1)
    raw = _elevator(addr_tree["building"].id, number=2, commissioned=False)
    foreign = _elevator(addr_tree["other"].id, number=1)
    repairing = _elevator(addr_tree["building"].id, number=3, status="under_repair")
    repairing.status_since = datetime(2026, 9, 1, 7, 30, tzinfo=timezone.utc)
    maintained = _elevator(addr_tree["building"].id, number=4, status="maintenance")
    broken = _elevator(addr_tree["building"].id, number=5, status="not_working")
    db_session.add_all([ok, raw, foreign, repairing, maintained, broken])
    await db_session.commit()
    return {"ok": ok, "raw": raw, "foreign": foreign, "repairing": repairing,
            "maintained": maintained, "broken": broken}


@pytest_asyncio.fixture
async def applicant(db_session: AsyncSession, addr_tree):
    user = User(telegram_id=111, username="appl", first_name="A",
                roles='["applicant"]', status="approved", phone="+700", language="ru")
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserApartment(user_id=user.id, apartment_id=addr_tree["apt"].id,
                                 status="approved"))
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def inspector(db_session: AsyncSession):
    user = User(telegram_id=222, username="insp", first_name="I",
                roles='["inspector"]', status="approved", phone="+701", language="ru")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def make_client(db_session_factory):
    def _make(user: User) -> AsyncClient:
        async def override_get_db():
            async with db_session_factory() as session:
                try:
                    yield session
                except Exception:
                    await session.rollback()
                    raise

        async def override_user():
            return user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_user
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield _make
    app.dependency_overrides.clear()


def _body(address_type: str, address_id: int, **extra) -> dict:
    body = {"category": "elevator", "urgency": "high", "description": "Лифт стоит",
            "address_type": address_type, "address_id": address_id}
    body.update(extra)
    return body


async def _row(db_session: AsyncSession, number: str) -> RequestModel:
    return (await db_session.execute(
        select(RequestModel).where(RequestModel.request_number == number)
    )).scalar_one()


# ── TWA (житель) ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_twa_elevator_category_without_fields_422(make_client, applicant, addr_tree, elevators):
    async with make_client(applicant) as ac:
        r = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id))
    assert r.status_code == 422, r.text
    assert "elevator_id" in r.text and "elevator_operational" in r.text


@pytest.mark.asyncio
async def test_twa_elevator_category_only_one_field_422(make_client, applicant, addr_tree, elevators):
    async with make_client(applicant) as ac:
        r = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id,
                                         elevator_id=elevators["ok"].id))
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_twa_elevator_valid_201_with_card_fields(make_client, applicant, addr_tree,
                                                       elevators, db_session):
    async with make_client(applicant) as ac:
        r = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id,
                                         elevator_id=elevators["ok"].id,
                                         elevator_operational=False))
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["elevator_id"] == elevators["ok"].id
    assert data["elevator_status"] == "working"
    assert "ул. Ленина 1" in data["elevator_label"]
    assert "подъезд 1" in data["elevator_label"] and "лифт 1" in data["elevator_label"]
    row = await _row(db_session, data["request_number"])
    assert row.elevator_id == elevators["ok"].id and row.elevator_operational is False


@pytest.mark.asyncio
async def test_twa_uncommissioned_elevator_422(make_client, applicant, addr_tree, elevators, db_session):
    async with make_client(applicant) as ac:
        r = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id,
                                         elevator_id=elevators["raw"].id,
                                         elevator_operational=True))
    assert r.status_code == 422, r.text
    assert "не введён" in r.json()["detail"]
    assert (await db_session.execute(select(RequestModel))).scalars().all() == []


@pytest.mark.asyncio
async def test_twa_unknown_elevator_422(make_client, applicant, addr_tree, elevators):
    async with make_client(applicant) as ac:
        r = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id,
                                         elevator_id=999_999, elevator_operational=True))
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_twa_other_category_with_elevator_201(make_client, applicant, addr_tree,
                                                    elevators, db_session):
    """Лифт у заявки иной категории допустим — поля пишутся как есть."""
    async with make_client(applicant) as ac:
        r = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id,
                                         category="electricity",
                                         elevator_id=elevators["ok"].id,
                                         elevator_operational=True))
    assert r.status_code == 201, r.text
    row = await _row(db_session, r.json()["request_number"])
    assert row.elevator_id == elevators["ok"].id and row.elevator_operational is True


@pytest.mark.asyncio
async def test_twa_other_category_without_elevator_201(make_client, applicant, addr_tree):
    async with make_client(applicant) as ac:
        r = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id, category="electricity"))
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["elevator_id"] is None and data["elevator_label"] is None
    assert data["elevator_status"] is None


@pytest.mark.asyncio
async def test_twa_flag_off_fields_ignored(make_client, applicant, addr_tree, elevators,
                                           db_session, monkeypatch):
    """Флаг выключен: категория «лифт» без полей — как раньше; поля не пишутся."""
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    async with make_client(applicant) as ac:
        r1 = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id))
        r2 = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id,
                                          elevator_id=elevators["raw"].id,
                                          elevator_operational=True))
    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text
    for resp in (r1, r2):
        row = await _row(db_session, resp.json()["request_number"])
        assert row.elevator_id is None and row.elevator_operational is None
        assert resp.json()["elevator_id"] is None


@pytest.mark.asyncio
async def test_twa_elevator_of_other_building_422(make_client, applicant, addr_tree, elevators,
                                                  db_session):
    """Security T6: лифт чужого дома к своей квартире не привязать (IDOR/перебор)."""
    async with make_client(applicant) as ac:
        r = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id,
                                         elevator_id=elevators["foreign"].id,
                                         elevator_operational=False))
    assert r.status_code == 422, r.text
    assert "другому дому" in r.json()["detail"]
    assert (await db_session.execute(select(RequestModel))).scalars().all() == []


@pytest.mark.asyncio
async def test_twa_elevator_category_on_yard_level_422(make_client, applicant, addr_tree, elevators):
    """Двор — дома нет → лифт привязать нельзя (проверка принадлежности не пропускается)."""
    async with make_client(applicant) as ac:
        r = await ac.post(URL, json=_body("yard", addr_tree["yard"].id,
                                         elevator_id=elevators["ok"].id,
                                         elevator_operational=False))
    assert r.status_code == 422, r.text
    assert "нужен дом или квартира" in r.json()["detail"]


# ── Инспектор ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inspector_elevator_of_other_building_422(make_client, inspector, addr_tree, elevators):
    async with make_client(inspector) as ac:
        r = await ac.post(f"{URL}/inspector", json=_body(
            "building", addr_tree["building"].id,
            elevator_id=elevators["foreign"].id, elevator_operational=True,
        ))
    assert r.status_code == 422, r.text
    assert "другому дому" in r.json()["detail"]


@pytest.mark.asyncio
async def test_inspector_elevator_without_fields_422(make_client, inspector, addr_tree, elevators):
    async with make_client(inspector) as ac:
        r = await ac.post(f"{URL}/inspector", json=_body("building", addr_tree["building"].id))
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_inspector_elevator_valid_201(make_client, inspector, addr_tree, elevators, db_session):
    async with make_client(inspector) as ac:
        r = await ac.post(f"{URL}/inspector", json=_body(
            "building", addr_tree["building"].id,
            elevator_id=elevators["ok"].id, elevator_operational=True,
        ))
    assert r.status_code == 201, r.text
    assert r.json()["elevator_id"] == elevators["ok"].id
    assert r.json()["elevator_status"] == "working"
    row = await _row(db_session, r.json()["request_number"])
    assert row.elevator_operational is True and row.source == "inspector"


# ── Р18: лифт «В ремонте»/«На ТО» ────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("key,status", [("repairing", "under_repair"), ("maintained", "maintenance")])
async def test_twa_elevator_under_works_409(make_client, applicant, addr_tree, elevators,
                                            db_session, key, status):
    """Житель по лифту в работах получает 409 с машинным кодом; заявки нет."""
    async with make_client(applicant) as ac:
        r = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id,
                                         elevator_id=elevators[key].id,
                                         elevator_operational=False))
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "elevator_under_works"
    assert detail["status"] == status
    assert "ул. Ленина 1" in detail["label"]
    assert (await db_session.execute(select(RequestModel))).scalars().all() == []


@pytest.mark.asyncio
async def test_twa_under_works_409_carries_status_since(make_client, applicant, addr_tree,
                                                        elevators):
    async with make_client(applicant) as ac:
        r = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id,
                                         elevator_id=elevators["repairing"].id,
                                         elevator_operational=False))
    assert r.json()["detail"]["status_since"].startswith("2026-09-01T07:30")


@pytest.mark.asyncio
async def test_twa_not_working_elevator_still_201(make_client, applicant, addr_tree, elevators):
    """Регресс: «не работает» — не «идут работы», заявка создаётся как раньше."""
    async with make_client(applicant) as ac:
        r = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id,
                                         elevator_id=elevators["broken"].id,
                                         elevator_operational=False))
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_twa_flag_off_does_not_block_under_works(make_client, applicant, addr_tree,
                                                       elevators, monkeypatch):
    monkeypatch.setattr(settings, "ELEVATORS_ENABLED", False)
    async with make_client(applicant) as ac:
        r = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id,
                                         elevator_id=elevators["repairing"].id,
                                         elevator_operational=False))
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_inspector_under_works_201(make_client, inspector, addr_tree, elevators, db_session):
    """Лазейка персонала: обходчик создаёт заявку по лифту в ремонте."""
    async with make_client(inspector) as ac:
        r = await ac.post(f"{URL}/inspector", json=_body(
            "building", addr_tree["building"].id,
            elevator_id=elevators["repairing"].id, elevator_operational=False,
        ))
    assert r.status_code == 201, r.text
    row = await _row(db_session, r.json()["request_number"])
    assert row.elevator_id == elevators["repairing"].id


@pytest.mark.asyncio
async def test_uncommissioned_elevator_still_422_not_409(make_client, applicant, addr_tree,
                                                         elevators):
    """Обычная ошибка Р11 осталась 422 — 409 только у Р18."""
    async with make_client(applicant) as ac:
        r = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id,
                                         elevator_id=elevators["raw"].id,
                                         elevator_operational=True))
    assert r.status_code == 422, r.text


# ── RequestCard: канбан / список / деталь ────────────────────────────

def _seed_request(number: str, *, user_id: int, elevator_id: int | None, category: str) -> RequestModel:
    return RequestModel(
        request_number=number, user_id=user_id, category=category, urgency="high",
        description="d", address="ул. Ленина 1", status="Новая", source="twa",
        media_files=[], elevator_id=elevator_id,
        elevator_operational=False if elevator_id is not None else None,
    )


@pytest.mark.asyncio
async def test_kanban_cards_carry_elevator_fields(client, db_session, manager_user, elevators):
    db_session.add_all([
        _seed_request("260905-001", user_id=manager_user.id, elevator_id=elevators["ok"].id,
                      category="elevator"),
        _seed_request("260905-002", user_id=manager_user.id, elevator_id=None,
                      category="electricity"),
    ])
    await db_session.commit()

    payload = (await client.get(f"{URL}/kanban")).json()
    cards = {c["request_number"]: c
             for col in payload["columns"] for c in col["requests"]}
    with_lift, without = cards["260905-001"], cards["260905-002"]
    assert with_lift["elevator_id"] == elevators["ok"].id
    assert with_lift["elevator_status"] == "working"
    assert "ул. Ленина 1" in with_lift["elevator_label"]
    assert without["elevator_id"] is None
    assert without["elevator_label"] is None and without["elevator_status"] is None


@pytest.mark.asyncio
async def test_list_and_detail_carry_elevator_fields(client, db_session, manager_user, elevators):
    db_session.add(_seed_request("260905-003", user_id=manager_user.id,
                                 elevator_id=elevators["ok"].id, category="elevator"))
    await db_session.commit()

    listed = (await client.get(URL)).json()
    assert listed[0]["elevator_label"] and listed[0]["elevator_status"] == "working"
    detail = (await client.get(f"{URL}/260905-003")).json()
    assert detail["elevator_id"] == elevators["ok"].id
    assert "подъезд 1" in detail["elevator_label"]


# ── Р18a: тумблер менеджера ──────────────────────────────────────────


async def _set_toggle(db_session: AsyncSession, allowed: bool) -> None:
    """Записать elevators_config.allow_resident_requests_under_works."""
    from uk_management_bot.services.elevator_service import merge_config

    db_session.add(ElevatorsConfig(
        id=1, data=merge_config(None, {"allow_resident_requests_under_works": allowed}),
    ))
    await db_session.commit()


@pytest.mark.asyncio
async def test_toggle_on_lets_resident_create_under_works(make_client, applicant, addr_tree,
                                                          elevators, db_session):
    """Менеджер разрешил — TWA-житель снова создаёт заявку (201)."""
    await _set_toggle(db_session, True)
    async with make_client(applicant) as ac:
        r = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id,
                                         elevator_id=elevators["repairing"].id,
                                         elevator_operational=False))
    assert r.status_code == 201, r.text
    row = await _row(db_session, r.json()["request_number"])
    assert row.elevator_id == elevators["repairing"].id


@pytest.mark.asyncio
async def test_toggle_off_explicitly_still_409(make_client, applicant, addr_tree, elevators,
                                               db_session):
    await _set_toggle(db_session, False)
    async with make_client(applicant) as ac:
        r = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id,
                                         elevator_id=elevators["repairing"].id,
                                         elevator_operational=False))
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "elevator_under_works"


@pytest.mark.asyncio
async def test_for_building_carries_resident_verdict_blocked(make_client, applicant, addr_tree,
                                                             elevators):
    """TWA получает готовый вердикт, а не конфиг: запрет включён (дефолт)."""
    async with make_client(applicant) as ac:
        r = await ac.get(f"/api/v2/elevators/for-building/{addr_tree['building'].id}")
    assert r.status_code == 200, r.text
    by_id = {item["id"]: item for item in r.json()}
    assert by_id[elevators["repairing"].id]["resident_request_blocked"] is True
    assert by_id[elevators["maintained"].id]["resident_request_blocked"] is True
    assert by_id[elevators["ok"].id]["resident_request_blocked"] is False
    assert by_id[elevators["broken"].id]["resident_request_blocked"] is False
    assert by_id[elevators["repairing"].id]["status_since"].startswith("2026-09-01T07:30")


@pytest.mark.asyncio
async def test_for_building_verdict_follows_toggle(make_client, applicant, addr_tree, elevators,
                                                   db_session):
    await _set_toggle(db_session, True)
    async with make_client(applicant) as ac:
        r = await ac.get(f"/api/v2/elevators/for-building/{addr_tree['building'].id}")
    by_id = {item["id"]: item for item in r.json()}
    assert by_id[elevators["repairing"].id]["resident_request_blocked"] is False


@pytest_asyncio.fixture
async def uz_applicant(db_session: AsyncSession, addr_tree):
    """Житель с языком uz — проверяем локализацию подписи в теле 409."""
    user = User(telegram_id=333, username="uzappl", first_name="U",
                roles='["applicant"]', status="approved", phone="+702", language="uz")
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserApartment(user_id=user.id, apartment_id=addr_tree["apt"].id,
                                 status="approved"))
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_409_label_uses_requester_language(make_client, uz_applicant, addr_tree, elevators):
    """UZ-житель получает UZ-подпись лифта (RU-подпись в UZ-уведомлении — баг)."""
    async with make_client(uz_applicant) as ac:
        r = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id,
                                         elevator_id=elevators["repairing"].id,
                                         elevator_operational=False))
    assert r.status_code == 409, r.text
    label = r.json()["detail"]["label"]
    assert "kirish" in label and "lift" in label
    assert "подъезд" not in label


@pytest.mark.asyncio
async def test_409_label_default_language_is_ru(make_client, applicant, addr_tree, elevators):
    async with make_client(applicant) as ac:
        r = await ac.post(URL, json=_body("apartment", addr_tree["apt"].id,
                                         elevator_id=elevators["repairing"].id,
                                         elevator_operational=False))
    assert "подъезд" in r.json()["detail"]["label"]


@pytest.mark.asyncio
async def test_for_building_skips_config_read_when_nothing_under_works(
    make_client, applicant, addr_tree, db_session, monkeypatch,
):
    """Штатный путь (все лифты работают) не трогает строку elevators_config."""
    from uk_management_bot.api.elevators import service as elevators_service

    working_only = _elevator(addr_tree["building"].id, number=1)
    broken = _elevator(addr_tree["building"].id, number=2, status="not_working")
    db_session.add_all([working_only, broken])
    await db_session.commit()

    calls = 0
    original = elevators_service.domain.load_config_async

    async def _spy(db):
        nonlocal calls
        calls += 1
        return await original(db)

    monkeypatch.setattr(elevators_service.domain, "load_config_async", _spy)

    async with make_client(applicant) as ac:
        r = await ac.get(f"/api/v2/elevators/for-building/{addr_tree['building'].id}")
    assert r.status_code == 200, r.text
    assert calls == 0, "конфиг прочитан, хотя под работами нет ни одного лифта"
    assert all(item["resident_request_blocked"] is False for item in r.json())


@pytest.mark.asyncio
async def test_for_building_reads_config_once_when_something_under_works(
    make_client, applicant, addr_tree, elevators, monkeypatch,
):
    """Есть лифт под работами — конфиг читается РОВНО один раз на страницу."""
    from uk_management_bot.api.elevators import service as elevators_service

    calls = 0
    original = elevators_service.domain.load_config_async

    async def _spy(db):
        nonlocal calls
        calls += 1
        return await original(db)

    monkeypatch.setattr(elevators_service.domain, "load_config_async", _spy)

    async with make_client(applicant) as ac:
        r = await ac.get(f"/api/v2/elevators/for-building/{addr_tree['building'].id}")
    assert r.status_code == 200, r.text
    assert calls == 1
    by_id = {item["id"]: item for item in r.json()}
    assert by_id[elevators["repairing"].id]["resident_request_blocked"] is True
