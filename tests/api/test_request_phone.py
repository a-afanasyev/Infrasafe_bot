"""Кнопка «Запросить номер телефона» с дашборда (сотрудник и житель).

Менеджер жмёт кнопку → API шлёт пользователю в Telegram сообщение с
request_contact-клавиатурой; сам номер появится позже, когда пользователь
поделится контактом (stateless-хендлер бота `handlers/phone_share.py`).

Проверяем HTTP-контракт и ПОЛЕЗНУЮ НАГРУЗКУ Telegram-вызова (сеть мокается
на границе `_send` модуля `api/users/phone_request.py`): без request_contact
в клавиатуре фича мертва, а тест эндпоинта «200 OK» этого не увидел бы.
"""
from unittest.mock import AsyncMock

import pytest

from uk_management_bot.api.users import phone_request
from uk_management_bot.database.models.user import User


async def _user(db, tg, *, roles='["applicant", "executor"]', active_role="executor"):
    u = User(
        telegram_id=tg,
        username=f"u{tg}", first_name="U", last_name=str(tg),
        roles=roles, active_role=active_role,
        status="approved", verification_status="verified",
        language="ru",
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.fixture
def sent(monkeypatch):
    """Мок сетевой границы; собирает (chat_id, payload)."""
    calls: list[tuple[int, dict]] = []

    async def fake_send(chat_id: int, payload: dict) -> str:
        calls.append((chat_id, payload))
        return phone_request.VERDICT_OK

    monkeypatch.setattr(phone_request, "_send", fake_send)
    return calls


@pytest.mark.asyncio
async def test_employee_request_phone_sends_contact_keyboard(client, db_session, sent):
    emp = await _user(db_session, 7001)

    resp = await client.post(f"/api/v2/shifts/employees/{emp.id}/request-phone")

    assert resp.status_code == 200
    assert resp.json() == {"sent": True}
    assert len(sent) == 1
    chat_id, payload = sent[0]
    assert chat_id == 7001
    buttons = payload["reply_markup"]["keyboard"]
    assert any(btn.get("request_contact") is True for row in buttons for btn in row)


@pytest.mark.asyncio
async def test_employee_not_found_404(client, sent):
    resp = await client.post("/api/v2/shifts/employees/999999/request-phone")
    assert resp.status_code == 404
    assert sent == []


@pytest.mark.asyncio
async def test_telegram_refusal_becomes_502(client, db_session, monkeypatch):
    emp = await _user(db_session, 7003)
    monkeypatch.setattr(
        phone_request, "_send", AsyncMock(return_value=phone_request.VERDICT_ERROR))

    resp = await client.post(f"/api/v2/shifts/employees/{emp.id}/request-phone")

    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_blocked_bot_becomes_409_with_reason(client, db_session, monkeypatch):
    """Прод-случай 2026-09-01: житель заблокировал бота — менеджер видел общее
    «Telegram delivery failed» и считал фичу сломанной. Причина обязана дойти."""
    emp = await _user(db_session, 7004)
    monkeypatch.setattr(
        phone_request, "_send", AsyncMock(return_value=phone_request.VERDICT_BLOCKED))

    resp = await client.post(f"/api/v2/shifts/employees/{emp.id}/request-phone")

    assert resp.status_code == 409
    assert "заблокировал" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_no_chat_becomes_409_with_reason(client, db_session, monkeypatch):
    emp = await _user(db_session, 7005)
    monkeypatch.setattr(
        phone_request, "_send", AsyncMock(return_value=phone_request.VERDICT_NO_CHAT))

    resp = await client.post(f"/api/v2/shifts/employees/{emp.id}/request-phone")

    assert resp.status_code == 409
    assert "не открывал" in resp.json()["detail"]


@pytest.mark.parametrize("status,description,expected", [
    (200, "", "ok"),
    (403, "Forbidden: bot was blocked by the user", "blocked"),
    (403, "Forbidden: user is deactivated", "blocked"),
    (400, "Bad Request: chat not found", "no_chat"),
    (400, "Bad Request: message is too long", "error"),
    (500, "", "error"),
])
def test_classify_telegram_refusals(status, description, expected):
    assert phone_request._classify(status, description) == expected


@pytest.mark.asyncio
async def test_resident_request_phone_sends_contact_keyboard(client, db_session, sent):
    resident = await _user(
        db_session, 7101, roles='["applicant"]', active_role="applicant",
    )

    resp = await client.post(f"/api/v2/residents/{resident.id}/request-phone")

    assert resp.status_code == 200
    assert resp.json() == {"sent": True}
    chat_id, payload = sent[0]
    assert chat_id == 7101
    buttons = payload["reply_markup"]["keyboard"]
    assert any(btn.get("request_contact") is True for row in buttons for btn in row)


@pytest.mark.asyncio
async def test_resident_not_found_404(client, sent):
    resp = await client.post("/api/v2/residents/999999/request-phone")
    assert resp.status_code == 404
    assert sent == []
