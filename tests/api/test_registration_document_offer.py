"""После регистрации в TWA житель получает в боте кнопку загрузки документа.

Решение владельца 2026-11-03: документ на квартиру обязателен, а загрузка с
шифрованием живёт только в боте. Кнопка уходит из ЕДИНОГО успешного выхода
`register_applicant`, поэтому повтор регистрации восстанавливает потерянное
сообщение; сбой Telegram регистрацию не валит (дальше выручает /start).
"""
import uuid
from unittest.mock import AsyncMock

import pytest

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.keyboards.documents_entry import UPLOAD_DOCUMENTS_CB

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _mute_managers(monkeypatch):
    monkeypatch.setattr(
        "uk_management_bot.api.registration.router.notify_managers_new_registration", AsyncMock())


@pytest.fixture
def send(monkeypatch):
    m = AsyncMock(return_value=type("R", (), {"ok": True})())
    monkeypatch.setattr("uk_management_bot.api.telegram_send.send_message", m)
    return m


async def _resident_with_apartment(db, telegram_id: int) -> int:
    db.add(User(telegram_id=telegram_id, status="pending", phone="+998901112233", language="uz"))
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


async def _register(client, tid: int, apt_id: int):
    """Каждая попытка — со свежим тикетом, как после `/start`: завершённая
    регистрация гасит прежний (AUTH-03)."""
    from uk_management_bot.api.registration.tickets import issue_registration_ticket
    ticket = await issue_registration_ticket(tid)
    return await client.post("/api/v2/registration/applicant",
                             headers={"Authorization": f"Bearer {ticket}"},
                             json={"full_name": "Иван Иванов", "apartment_id": apt_id})


def _upload_button_calls(send_mock):
    calls = []
    for call in send_mock.await_args_list:
        markup = call.kwargs.get("reply_markup") or {}
        cbs = [b.get("callback_data") for row in markup.get("inline_keyboard", []) for b in row]
        if UPLOAD_DOCUMENTS_CB in cbs:
            calls.append(call)
    return calls


async def test_new_and_repeat_registration_both_send_button(client, db_session, send):
    apt_id = await _resident_with_apartment(db_session, 99700)
    for _ in range(2):
        r = await _register(client, 99700, apt_id)
        assert r.status_code == 200, r.text

    calls = _upload_button_calls(send)
    assert [c.args[0] for c in calls] == [99700, 99700]
    # Клавиатура — JSON-словарь (модуль шлёт JSON), текст — на языке жителя.
    assert isinstance(calls[0].kwargs["reply_markup"], dict)
    from uk_management_bot.utils.helpers import get_text
    assert calls[0].args[1] == get_text("onboarding.documents.description", language="uz")


async def test_telegram_failure_does_not_fail_registration(client, db_session, monkeypatch):
    monkeypatch.setattr("uk_management_bot.api.telegram_send.send_message",
                        AsyncMock(side_effect=RuntimeError("telegram down")))
    apt_id = await _resident_with_apartment(db_session, 99701)
    r = await _register(client, 99701, apt_id)
    assert r.status_code == 200 and r.json()["status"] == "pending"


async def test_start_returns_site_names_for_welcome(client, monkeypatch):
    """Приветствие формы берёт имена ЖК/УК из тех же настроек, что и бот."""
    import hashlib
    import hmac
    import json
    import time
    from urllib.parse import urlencode

    monkeypatch.setattr(settings, "RESIDENTIAL_COMPLEX_NAME", "Olmazor Business City")
    monkeypatch.setattr(settings, "MANAGEMENT_COMPANY_NAME", "")
    user = json.dumps({"id": 99702, "first_name": "Test"}, separators=(",", ":"))
    fields = {"auth_date": str(int(time.time())), "user": user}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()

    r = await client.post("/api/v2/registration/start", json={"init_data": urlencode(fields)})
    assert r.status_code == 200, r.text
    assert r.json()["complex_name"] == "Olmazor Business City"
    assert r.json()["company_name"] == ""
