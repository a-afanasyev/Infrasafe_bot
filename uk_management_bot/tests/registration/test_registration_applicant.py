import pytest
from unittest.mock import AsyncMock, patch
from uk_management_bot.api.registration.notify import notify_managers_new_registration


@pytest.mark.asyncio
async def test_notify_swallows_errors(monkeypatch):
    monkeypatch.setattr("uk_management_bot.config.settings.settings.ADMIN_USER_IDS", [111])
    with patch("uk_management_bot.api.registration.notify._send", new=AsyncMock(side_effect=Exception("boom"))):
        # must NOT raise
        await notify_managers_new_registration(telegram_id=5, full_name="Иван", apartment_label="Двор-1, кв 12")


def _bearer(tid):
    from uk_management_bot.api.registration.tickets import create_registration_ticket
    return {"Authorization": f"Bearer {create_registration_ticket(tid)}"}


@pytest.fixture
def mock_notify(monkeypatch):
    """Never hit the real Telegram API in tests."""
    from unittest.mock import AsyncMock
    m = AsyncMock()
    monkeypatch.setattr(
        "uk_management_bot.api.registration.router.notify_managers_new_registration", m)
    return m


@pytest.mark.asyncio
async def test_applicant_no_ticket_401(api_client, mock_notify):
    r = await api_client.post("/api/v2/registration/applicant",
        json={"full_name": "Иван Иванов", "apartment_id": 1})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_applicant_creates_pending(api_client, async_db, seed_user, seed_apartment, mock_notify):
    from sqlalchemy import select
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.models.user_apartment import UserApartment
    from uk_management_bot.utils.auth_helpers import parse_roles_safe
    # телефон — только из контакта, уже сохранён ботом (спека §4.4)
    await seed_user(telegram_id=99100, phone="+998901112233")
    apt_id = (await seed_apartment()).id
    r = await api_client.post("/api/v2/registration/applicant",
        headers=_bearer(99100),
        json={"full_name": "Иван Иванов", "apartment_id": apt_id})
    assert r.status_code == 200 and r.json()["status"] == "pending"
    user = (await async_db.execute(select(User).where(User.telegram_id == 99100))).scalar_one()
    assert user.status == "pending"
    assert user.active_role == "applicant"
    assert "applicant" in parse_roles_safe(user.roles)
    assert user.phone == "+998901112233"
    ua = (await async_db.execute(
        select(UserApartment).where(UserApartment.user_id == user.id))).scalar_one()
    assert ua.status == "pending" and ua.apartment_id == apt_id


@pytest.mark.asyncio
async def test_applicant_double_submit_idempotent(api_client, async_db, seed_user, seed_apartment, mock_notify):
    from sqlalchemy import select, func
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.models.user_apartment import UserApartment
    await seed_user(telegram_id=99200, phone="+998901112233")
    apt_id = (await seed_apartment()).id
    payload = {"full_name": "Иван Иванов", "apartment_id": apt_id}
    r1 = await api_client.post("/api/v2/registration/applicant", headers=_bearer(99200), json=payload)
    r2 = await api_client.post("/api/v2/registration/applicant", headers=_bearer(99200), json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
    user = (await async_db.execute(select(User).where(User.telegram_id == 99200))).scalar_one()
    count = (await async_db.execute(
        select(func.count()).select_from(UserApartment).where(UserApartment.user_id == user.id))).scalar()
    assert count == 1


@pytest.mark.asyncio
async def test_applicant_inactive_building_400(api_client, async_db, seed_user, seed_apartment, mock_notify):
    from sqlalchemy import select
    u = await seed_user(telegram_id=99400, phone="+998901112233")
    apt_id = (await seed_apartment(building_active=False)).id
    r = await api_client.post("/api/v2/registration/applicant",
        headers=_bearer(99400),
        json={"full_name": "Иван", "apartment_id": apt_id})
    assert r.status_code == 400
    from sqlalchemy import func
    from uk_management_bot.database.models.user_apartment import UserApartment
    count = (await async_db.execute(
        select(func.count()).select_from(UserApartment).where(UserApartment.user_id == u.id))).scalar()
    assert count == 0


@pytest.mark.asyncio
async def test_applicant_unknown_apartment_400(api_client, async_db, seed_user, mock_notify):
    from sqlalchemy import select
    u = await seed_user(telegram_id=99300, phone="+998901112233")
    r = await api_client.post("/api/v2/registration/applicant",
        headers=_bearer(99300),
        json={"full_name": "Иван", "apartment_id": 999999})
    assert r.status_code == 400
    from sqlalchemy import func
    from uk_management_bot.database.models.user_apartment import UserApartment
    count = (await async_db.execute(
        select(func.count()).select_from(UserApartment).where(UserApartment.user_id == u.id))).scalar()
    assert count == 0


@pytest.mark.asyncio
async def test_applicant_without_phone_409(api_client, async_db, seed_user, seed_apartment, mock_notify):
    """Телефон только из Telegram-контакта (спека §4.4): нет в БД — 409, ни
    пользователя, ни заявки не создаём; телефон в теле игнорируется."""
    from sqlalchemy import select
    from uk_management_bot.database.models.user import User

    apt_id = (await seed_apartment()).id
    r = await api_client.post("/api/v2/registration/applicant",
        headers=_bearer(99101),
        json={"full_name": "Иван", "phone": "+998901112233", "apartment_id": apt_id})
    assert r.status_code == 409
    assert "контакт" in r.json()["detail"].lower()
    assert (await async_db.execute(select(User).where(User.telegram_id == 99101))).scalar_one_or_none() is None

    await seed_user(telegram_id=99102, phone=None)
    r = await api_client.post("/api/v2/registration/applicant",
        headers=_bearer(99102),
        json={"full_name": "Иван", "apartment_id": apt_id})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_applicant_blocked_user_403(api_client, seed_user, seed_apartment, mock_notify):
    await seed_user(telegram_id=99500, status="blocked")
    apt_id = (await seed_apartment()).id
    r = await api_client.post("/api/v2/registration/applicant",
        headers=_bearer(99500),
        json={"full_name": "Иван", "apartment_id": apt_id})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_applicant_privileged_pending_rejected_403(api_client, async_db, seed_apartment, mock_notify):
    """SEC-06: self-регистрация НЕ должна перетирать pre-provisioned аккаунт.

    Pending-аккаунт с ролью executor (заведён менеджером) при валидном тикете НЕ
    должен получить перезапись ФИО/телефона и active_role="applicant" — 403, поля
    остаются нетронутыми.
    """
    import json
    from sqlalchemy import select
    from uk_management_bot.database.models.user import User
    u = User(
        telegram_id=99600, status="pending",
        first_name="Пётр", last_name="Смирнов", phone="+998900000000",
        roles=json.dumps(["executor"]), active_role="executor",
    )
    async_db.add(u)
    await async_db.flush()
    apt_id = (await seed_apartment()).id
    r = await api_client.post("/api/v2/registration/applicant",
        headers=_bearer(99600),
        json={"full_name": "Иван Иванов", "apartment_id": apt_id})
    assert r.status_code == 403
    user = (await async_db.execute(select(User).where(User.telegram_id == 99600))).scalar_one()
    assert user.first_name == "Пётр"
    assert user.last_name == "Смирнов"
    assert user.phone == "+998900000000"
    assert user.active_role == "executor"


@pytest.mark.asyncio
async def test_applicant_plain_pending_still_allowed(api_client, async_db, seed_user, seed_apartment, mock_notify):
    """SEC-06 не должен над-блокировать: pending без ролей (обычный инвайт) → 200."""
    await seed_user(telegram_id=99700, status="pending", phone="+998901112233")  # roles не заданы
    apt_id = (await seed_apartment()).id
    r = await api_client.post("/api/v2/registration/applicant",
        headers=_bearer(99700),
        json={"full_name": "Иван Иванов", "apartment_id": apt_id})
    assert r.status_code == 200 and r.json()["status"] == "pending"
