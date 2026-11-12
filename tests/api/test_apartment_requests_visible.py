"""Жилец видит заявки по своей квартире, кто бы их ни подал (решение владельца 2026-11-12).

Повод: заявку по звонку диспетчер оформил на квартиру 14V-54 с незнакомого
номера — она легла на диспетчера, и жильцы квартиры её не увидели. Заявки на
двор и дом (без квартиры) по-прежнему видит только заявитель.
"""
import pytest
import pytest_asyncio

from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services import workflow_notifications as wn


def _request(number, *, user_id, apartment=None, building=None, status="Новая"):
    return RequestModel(
        request_number=number, user_id=user_id, category="plumbing", urgency="low",
        description="течёт труба", status=status, source="call_center", media_files=[],
        apartment_id=apartment.id if apartment else None,
        building_id=building.id if building else None,
        address="адрес", address_type="apartment" if apartment else "building",
    )


@pytest_asyncio.fixture
async def world(db_session, resident_user):
    yard = Yard(name="Olmazor", is_active=True)
    db_session.add(yard)
    await db_session.flush()
    b14 = Building(address="Yangi Olmazor, 14V", yard_id=yard.id, is_active=True, entrance_count=1, floor_count=9)
    db_session.add(b14)
    await db_session.flush()
    a54 = Apartment(building_id=b14.id, apartment_number="54", is_active=True)
    a55 = Apartment(building_id=b14.id, apartment_number="55", is_active=True)
    dispatcher = User(telegram_id=700001, first_name="Dina", roles='["dispatcher"]',
                      active_role="dispatcher", status="approved")
    waiting = User(telegram_id=700002, first_name="Pending", roles='["applicant"]',
                   active_role="applicant", status="approved")
    db_session.add_all([a54, a55, dispatcher, waiting])
    await db_session.flush()
    db_session.add_all([
        UserApartment(user_id=resident_user.id, apartment_id=a54.id, status="approved"),
        UserApartment(user_id=waiting.id, apartment_id=a54.id, status="pending"),
        _request("261112-101", user_id=dispatcher.id, apartment=a54),                    # по звонку, его квартира
        _request("261112-102", user_id=dispatcher.id, apartment=a54, status="В работе"),
        _request("261112-103", user_id=dispatcher.id, building=b14),                     # на дом — не его
        _request("261112-104", user_id=dispatcher.id, apartment=a55),                    # чужая квартира
        _request("261112-105", user_id=resident_user.id, building=b14),                  # своя на дом
    ])
    await db_session.commit()
    return {"a54": a54, "dispatcher": dispatcher, "waiting": waiting}


def _as(user):
    async def _current():
        return user

    app.dependency_overrides[get_current_user] = _current


@pytest.mark.asyncio
async def test_resident_list_has_own_and_apartment_requests(client, world, resident_user):
    _as(resident_user)
    r = await client.get("/api/v2/requests", params={"view": "own", "limit": 50})
    assert r.status_code == 200, r.text
    assert {x["request_number"] for x in r.json()} == {"261112-101", "261112-102", "261112-105"}


@pytest.mark.asyncio
@pytest.mark.parametrize("number,expected", [
    ("261112-101", 200),   # заявка по его квартире, подал диспетчер, «Новая»
    ("261112-102", 200),   # она же в работе
    ("261112-103", 403),   # на дом — только заявитель
    ("261112-104", 403),   # чужая квартира
])
async def test_resident_opens_only_his_apartment_requests(client, world, resident_user, number, expected):
    _as(resident_user)
    assert (await client.get(f"/api/v2/requests/{number}")).status_code == expected


@pytest.mark.asyncio
async def test_unapproved_link_gives_nothing(client, world):
    _as(world["waiting"])
    r = await client.get("/api/v2/requests", params={"view": "own", "limit": 50})
    assert r.json() == []
    assert (await client.get("/api/v2/requests/261112-101")).status_code == 403


# ── что сосед НЕ может и чего не видит (секьюрити-ревью 2026-11-12) ──

@pytest.mark.asyncio
async def test_co_resident_does_not_see_who_called(client, db_session, world, resident_user, manager_user):
    """Имя и телефон звонящего диспетчеру — для сотрудников: звонить мог гость."""
    from sqlalchemy import update

    await db_session.execute(update(RequestModel).where(RequestModel.request_number == "261112-101").values(
        notes="Звонок: Рустам 905550011\nАдрес со слов звонящего: 3 этаж"))
    await db_session.commit()

    _as(resident_user)
    card = (await client.get("/api/v2/requests/261112-101")).json()
    assert card["notes"] == "Адрес со слов звонящего: 3 этаж"
    listed = (await client.get("/api/v2/requests", params={"view": "own", "limit": 50})).json()
    assert all("Звонок:" not in (x.get("notes") or "") for x in listed)

    _as(manager_user)
    assert "Звонок: Рустам" in (await client.get("/api/v2/requests/261112-101")).json()["notes"]


@pytest.mark.asyncio
async def test_co_resident_cannot_attach_photos(client, world, resident_user):
    """Сосед смотрит и комментирует; менять заявку — автор и менеджер.

    Отмену и возврат на доработку держит workflow-гвард (`_can_cancel`,
    `_owner_can_return` — только владелец), он от статуса доступа не зависит
    и покрыт своими тестами; здесь — путь, который расширялся вместе с доступом."""
    _as(resident_user)
    photo = await client.post(
        "/api/v2/media/upload",
        data={"request_number": "261112-101", "category": "request_photo"},
        files={"file": ("a.jpg", b"\xff\xd8\xff\xe0" + b"0" * 64, "image/jpeg")},
    )
    assert photo.status_code == 403, photo.text


# ── уведомления ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notifications_skip_inactive_residents_and_resident_executor(db_session, world, resident_user):
    a54, dispatcher = world["a54"], world["dispatcher"]
    blocked = User(telegram_id=700010, first_name="Blocked", roles='["applicant"]', status="blocked")
    lives_here_executor = User(telegram_id=700011, first_name="Exec", roles='["applicant", "executor"]',
                               status="approved")
    db_session.add_all([blocked, lives_here_executor])
    await db_session.flush()
    db_session.add_all([
        UserApartment(user_id=blocked.id, apartment_id=a54.id, status="approved"),
        UserApartment(user_id=lives_here_executor.id, apartment_id=a54.id, status="approved"),
    ])
    await db_session.commit()

    req = _request("v", user_id=dispatcher.id, apartment=a54)
    req.executor_id = lives_here_executor.id
    wanted = await wn._wanted_with_residents_async(db_session, req, {dispatcher.id})
    # заблокированному не пишем; исполнитель получает своё сообщение как исполнитель
    assert wanted == {dispatcher.id, resident_user.id}



@pytest.mark.asyncio
async def test_residents_are_notified_about_staff_filed_apartment_request(db_session, world, resident_user):
    dispatcher = world["dispatcher"]
    req = _request("x", user_id=dispatcher.id, apartment=world["a54"])
    wanted = await wn._wanted_with_residents_async(db_session, req, {dispatcher.id})
    # одобренный жилец добавлен, ожидающий привязки — нет; автор остаётся
    assert wanted == {dispatcher.id, resident_user.id}


@pytest.mark.asyncio
async def test_no_extra_recipients_when_author_lives_there_or_no_apartment(db_session, world, resident_user):
    own = _request("y", user_id=resident_user.id, apartment=world["a54"])
    assert await wn._wanted_with_residents_async(db_session, own, {resident_user.id}) == {resident_user.id}
    building_level = _request("z", user_id=world["dispatcher"].id)
    assert await wn._wanted_with_residents_async(
        db_session, building_level, {world["dispatcher"].id}) == {world["dispatcher"].id}
    # адресуемся не заявителю (только исполнителю) — жильцов не добавляем
    staff = _request("w", user_id=world["dispatcher"].id, apartment=world["a54"])
    assert await wn._wanted_with_residents_async(db_session, staff, {999}) == {999}
