"""A9-P3-20: машинные коды отказов регистрации.

Фронт ветвился regex'ом по тексту `detail` («уже», «контакт») — правка
формулировки на бэке молча ломала сценарий. Теперь 409 несут стабильный код в
заголовке `X-Error-Code`, а `detail` остаётся прежней строкой (обратная
совместимость: старый бандл SPA, открытый во время раскатки, рендерит его как
раньше; объект в `detail` уронил бы его рендер).
"""
import hashlib
import hmac
import json
import time
import uuid
from unittest.mock import AsyncMock
from urllib.parse import urlencode

import pytest

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.yard import Yard


def _bearer(tid: int) -> dict:
    from uk_management_bot.api.registration.tickets import create_registration_ticket
    return {"Authorization": f"Bearer {create_registration_ticket(tid)}"}


def _initdata(telegram_id: int) -> str:
    user = json.dumps({"id": telegram_id, "first_name": "Test"}, separators=(",", ":"))
    fields = {"auth_date": str(int(time.time())), "user": user}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture(autouse=True)
def _mock_notify(monkeypatch):
    monkeypatch.setattr(
        "uk_management_bot.api.registration.router.notify_managers_new_registration", AsyncMock())


async def _user(db, telegram_id: int, status: str = "pending", phone: str | None = None) -> User:
    u = User(telegram_id=telegram_id, status=status, phone=phone)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _apartment(db) -> int:
    y = Yard(name=f"Двор-{uuid.uuid4().hex[:8]}", is_active=True)
    db.add(y)
    await db.flush()
    b = Building(address="ул. Ленина 1", yard_id=y.id, is_active=True)
    db.add(b)
    await db.flush()
    a = Apartment(apartment_number="12", building_id=b.id, is_active=True)
    db.add(a)
    await db.commit()
    return a.id


async def _link(db, user_id: int, apartment_id: int, status: str) -> None:
    db.add(UserApartment(user_id=user_id, apartment_id=apartment_id, status=status))
    await db.commit()


def _apply(client, tid: int, apt_id: int):
    return client.post("/api/v2/registration/applicant", headers=_bearer(tid),
                       json={"full_name": "Иван Иванов", "apartment_id": apt_id})


@pytest.mark.asyncio
async def test_start_approved_code_already_registered(client, db_session):
    await _user(db_session, 99802, status="approved")
    r = await client.post("/api/v2/registration/start", json={"init_data": _initdata(99802)})
    assert r.status_code == 409
    assert r.headers["x-error-code"] == "already_registered"
    assert isinstance(r.json()["detail"], str)  # BC: detail — по-прежнему строка


@pytest.mark.asyncio
async def test_error_code_header_exposed_via_cors(client, db_session):
    """Кросс-ориджин (dev без прокси) браузер отдаёт JS только заголовки из
    Access-Control-Expose-Headers — без X-Error-Code фронт кода не увидит."""
    await _user(db_session, 99807, status="approved")
    r = await client.post(
        "/api/v2/registration/start",
        json={"init_data": _initdata(99807)},
        headers={"Origin": "http://localhost:5173"},
    )
    assert r.status_code == 409
    exposed = [h.strip().lower() for h in r.headers.get("access-control-expose-headers", "").split(",")]
    assert "x-error-code" in exposed


@pytest.mark.asyncio
async def test_applicant_approved_code_already_registered(client, db_session):
    await _user(db_session, 99803, status="approved", phone="+998901112233")
    r = await _apply(client, 99803, await _apartment(db_session))
    assert r.status_code == 409
    assert r.headers["x-error-code"] == "already_registered"


@pytest.mark.asyncio
async def test_applicant_without_phone_code_contact_required(client, db_session):
    r = await _apply(client, 99804, await _apartment(db_session))
    assert r.status_code == 409
    assert r.headers["x-error-code"] == "contact_required"
    assert isinstance(r.json()["detail"], str)


@pytest.mark.asyncio
async def test_applicant_already_resident_code(client, db_session):
    u = await _user(db_session, 99805, phone="+998901112233")
    apt_id = await _apartment(db_session)
    await _link(db_session, u.id, apt_id, "approved")
    r = await _apply(client, 99805, apt_id)
    assert r.status_code == 409
    assert r.headers["x-error-code"] == "already_resident"


@pytest.mark.asyncio
async def test_applicant_previous_rejected_code(client, db_session):
    u = await _user(db_session, 99806, phone="+998901112233")
    apt_id = await _apartment(db_session)
    await _link(db_session, u.id, apt_id, "rejected")
    r = await _apply(client, 99806, apt_id)
    assert r.status_code == 409
    assert r.headers["x-error-code"] == "previous_rejected"
