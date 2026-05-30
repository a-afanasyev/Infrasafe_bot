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
        json={"full_name": "Иван Иванов", "phone": "+998901112233", "apartment_id": 1})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_applicant_creates_pending(api_client, async_db, seed_apartment, mock_notify):
    from sqlalchemy import select
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.models.user_apartment import UserApartment
    from uk_management_bot.utils.auth_helpers import parse_roles_safe
    apt_id = (await seed_apartment()).id
    r = await api_client.post("/api/v2/registration/applicant",
        headers=_bearer(99100),
        json={"full_name": "Иван Иванов", "phone": "+998901112233", "apartment_id": apt_id})
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
async def test_applicant_double_submit_idempotent(api_client, async_db, seed_apartment, mock_notify):
    from sqlalchemy import select, func
    from uk_management_bot.database.models.user import User
    from uk_management_bot.database.models.user_apartment import UserApartment
    apt_id = (await seed_apartment()).id
    payload = {"full_name": "Иван Иванов", "phone": "+998901112233", "apartment_id": apt_id}
    r1 = await api_client.post("/api/v2/registration/applicant", headers=_bearer(99200), json=payload)
    r2 = await api_client.post("/api/v2/registration/applicant", headers=_bearer(99200), json=payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
    user = (await async_db.execute(select(User).where(User.telegram_id == 99200))).scalar_one()
    count = (await async_db.execute(
        select(func.count()).select_from(UserApartment).where(UserApartment.user_id == user.id))).scalar()
    assert count == 1


@pytest.mark.asyncio
async def test_applicant_inactive_building_400(api_client, async_db, seed_apartment, mock_notify):
    from sqlalchemy import select
    from uk_management_bot.database.models.user import User
    apt_id = (await seed_apartment(building_active=False)).id
    r = await api_client.post("/api/v2/registration/applicant",
        headers=_bearer(99400),
        json={"full_name": "Иван", "phone": "+998901112233", "apartment_id": apt_id})
    assert r.status_code == 400
    assert (await async_db.execute(select(User).where(User.telegram_id == 99400))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_applicant_unknown_apartment_rolls_back_user(api_client, async_db, mock_notify):
    from sqlalchemy import select
    from uk_management_bot.database.models.user import User
    r = await api_client.post("/api/v2/registration/applicant",
        headers=_bearer(99300),
        json={"full_name": "Иван", "phone": "+998901112233", "apartment_id": 999999})
    assert r.status_code == 400
    assert (await async_db.execute(select(User).where(User.telegram_id == 99300))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_applicant_bad_phone_400(api_client, seed_apartment, mock_notify):
    apt_id = (await seed_apartment()).id
    r = await api_client.post("/api/v2/registration/applicant",
        headers=_bearer(99101),
        json={"full_name": "Иван", "phone": "xxx", "apartment_id": apt_id})
    assert r.status_code in (400, 422)
