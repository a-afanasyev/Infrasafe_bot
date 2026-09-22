"""A9-P2-7 / A9-P2-8: сеть — не внутри транзакции запроса и не до ответа.

Класс дефекта (BUG-189, аудит #9): ручка держит request-scoped сессию
idle-in-transaction на время Telegram/HTTP и/или ждёт медленную отправку до
ответа — на медленном Telegram ответ дольше 30 с edge → 504 при уже
сохранённых данных (а повтор создания заявки даёт дубль).

Проверки — через сырой ASGI-вызов (`asgi_call`, журнал порядка) и
запоминающую фабрику сессий (`recording_db`): шпион сетевого вызова пишет в
журнал и фиксирует, держит ли какая-то из сессий запроса транзакцию.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.utils.request_workflow import EventIntent

pytestmark = pytest.mark.asyncio


def _as_user(user: User) -> None:
    async def _override():
        return user
    app.dependency_overrides[get_current_user] = _override


async def _applicant_with_apartment(db) -> tuple[User, Apartment]:
    yard = Yard(name="Двор A9", is_active=True)
    db.add(yard)
    await db.flush()
    building = Building(address="ул. Сетевая 1", yard_id=yard.id, is_active=True,
                        entrance_count=1, floor_count=5)
    db.add(building)
    await db.flush()
    apt = Apartment(building_id=building.id, apartment_number="7", is_active=True)
    user = User(telegram_id=515151, first_name="A", roles='["applicant"]',
                active_role="applicant", status="approved", phone="+700", language="ru")
    db.add_all([apt, user])
    await db.flush()
    db.add(UserApartment(user_id=user.id, apartment_id=apt.id, status="approved"))
    await db.commit()
    await db.refresh(user)
    await db.refresh(apt)
    return user, apt


# ─────────────────────────── A9-P2-7: POST /requests ───────────────────────


@pytest.fixture
def dispatch_spies(monkeypatch, recording_db):
    """Автодиспетч «назначил дежурного»; уведомление — медленный шпион."""
    from uk_management_bot.services import dispatch as dispatch_mod
    from uk_management_bot.services import workflow_notifications as wn

    probe: dict = {"log": [], "tx_at_dispatch": None, "tx_at_notify": None,
                   "notified": []}

    async def fake_enabled(_db=None):
        return True

    async def fake_run(session_factory, request_number, principal, command):
        probe["tx_at_dispatch"] = recording_db.any_in_transaction()
        probe["log"].append("dispatch")
        return SimpleNamespace(post_commit_intents=[
            EventIntent("notify", {"action": "manager_assign",
                                   "request_number": request_number}),
        ])

    async def slow_notify(request_number, intents, *args, **kwargs):
        probe["tx_at_notify"] = recording_db.any_in_transaction()
        probe["log"].append("notify")
        probe["notified"].append(request_number)
        await asyncio.sleep(0.05)  # «медленный Telegram»
        return 1

    async def noop(*_a, **_kw):
        return None

    monkeypatch.setattr(dispatch_mod, "_specialization_for", lambda _c: "electric")
    monkeypatch.setattr(dispatch_mod, "_auto_assign_enabled_async", fake_enabled)
    monkeypatch.setattr(dispatch_mod, "pick_duty_executor_id", lambda *_a, **_k: 4242)
    monkeypatch.setattr(dispatch_mod, "_publish_status_changed", noop)
    monkeypatch.setattr(
        "uk_management_bot.services.workflow_runner.run_command_async", fake_run)
    monkeypatch.setattr(wn, "dispatch_notify_intents_detached", slow_notify)
    return probe


async def test_create_request_notifies_after_response_without_open_tx(
    db_session, recording_db, asgi_call, dispatch_spies,
):
    user, apt = await _applicant_with_apartment(db_session)
    _as_user(user)
    log = dispatch_spies["log"]

    status, body = await asgi_call("POST", "/api/v2/requests", log, json={
        "category": "Электрика", "urgency": "low", "description": "Нет света в подъезде",
        "address_type": "apartment", "address_id": apt.id,
    })

    assert status == 201, body
    # Диспетч синхронный (карточка ответа отражает назначение), уведомление —
    # после ответа: медленный Telegram не задерживает 201.
    assert log == ["dispatch", "response", "notify"], log
    assert dispatch_spies["notified"] == [body["request_number"]]
    # Транзакция создания закрыта до диспетча и тем более до сети.
    assert dispatch_spies["tx_at_dispatch"] is False
    assert dispatch_spies["tx_at_notify"] is False


# ─────────────────────────── A9-P2-8(a): remind-applicant ──────────────────


async def _executed_request(db) -> User:
    applicant = User(telegram_id=626262, first_name="Ж", roles='["applicant"]',
                     active_role="applicant", status="approved", language="ru")
    db.add(applicant)
    await db.flush()
    db.add(RequestModel(
        request_number="260923-001", user_id=applicant.id, category="electric",
        status="Исполнено", description="демо", urgency="low", is_returned=False,
        manager_confirmed=False, address="ул. Сетевая 1",
        created_at=datetime.now(timezone.utc),
    ))
    await db.commit()
    return applicant


@pytest.fixture
def telegram_probe(telegram_api, recording_db):
    """Шпион транспорта Bot API: журнал + «держит ли запрос транзакцию»."""
    probe: dict = {"log": [], "tx": [], "status": 200, "body": {"ok": True, "result": {}}}

    async def handler(request):
        probe["tx"].append(recording_db.any_in_transaction())
        probe["log"].append("telegram")
        return httpx.Response(probe["status"], json=probe["body"])

    telegram_api.handler = handler
    return probe


async def test_remind_applicant_sends_without_open_tx(
    db_session, manager_user, recording_db, asgi_call, telegram_probe, telegram_api,
):
    await _executed_request(db_session)
    _as_user(manager_user)

    status, body = await asgi_call(
        "POST", "/api/v2/requests/260923-001/remind-applicant", telegram_probe["log"])

    assert status == 200 and body == {"ok": True}
    assert telegram_probe["tx"] == [False], "Telegram вызван при открытой транзакции"
    call = telegram_api.calls("sendMessage")[0]
    assert call["chat_id"] == 626262 and call["parse_mode"] == "HTML"
    assert "260923-001" in call["text"]


async def test_remind_applicant_blocked_bot_is_409_not_500(
    db_session, manager_user, recording_db, asgi_call, telegram_probe,
):
    await _executed_request(db_session)
    _as_user(manager_user)
    telegram_probe["status"] = 403
    telegram_probe["body"] = {"ok": False, "error_code": 403,
                              "description": "Forbidden: bot was blocked by the user"}

    status, body = await asgi_call(
        "POST", "/api/v2/requests/260923-001/remind-applicant", telegram_probe["log"])

    assert status == 409, body
    assert "заблокировал бота" in body["detail"]


async def test_remind_applicant_telegram_failure_is_502(
    db_session, manager_user, recording_db, asgi_call, telegram_probe,
):
    await _executed_request(db_session)
    _as_user(manager_user)
    telegram_probe["status"] = 500
    telegram_probe["body"] = {"ok": False, "description": "Internal"}

    status, _body = await asgi_call(
        "POST", "/api/v2/requests/260923-001/remind-applicant", telegram_probe["log"])

    assert status == 502


# ─────────────────────────── A9-P2-8(b): detached notify ───────────────────


async def test_detached_notify_sends_without_open_tx(
    db_session, db_session_factory, monkeypatch,
):
    """BackgroundTasks-вариант читает заявку и получателей, а шлёт уже без
    транзакции: SELECT открывал её и держал на все отправки."""
    from unittest.mock import MagicMock

    from uk_management_bot.services import workflow_notifications as wn
    from uk_management_bot.utils.request_workflow import Action

    applicant = await _executed_request(db_session)
    sessions: list = []

    def factory():
        session = db_session_factory()
        sessions.append(session)
        return session

    tx_at_send: list[bool] = []
    sent: list[int] = []

    async def fake_send(bot, telegram_id, text):
        tx_at_send.append(any(s.in_transaction() for s in sessions))
        sent.append(telegram_id)
        return True

    monkeypatch.setattr("uk_management_bot.database.session.AsyncSessionLocal", factory)
    monkeypatch.setattr(
        "uk_management_bot.services.notification_service.send_to_user", fake_send)
    monkeypatch.setattr(
        "uk_management_bot.services.notification_service._get_shared_bot",
        lambda: MagicMock())

    delivered = await wn.dispatch_notify_intents_detached("260923-001", [
        EventIntent("notify", {"action": Action.CLARIFY_REQUEST.value,
                               "request_number": "260923-001"}),
    ], clarification_text="какой подъезд?")

    assert delivered == 1 and sent == [applicant.telegram_id]
    assert sessions, "detached-вариант обязан открыть свою сессию"
    assert tx_at_send == [False], "отправка шла при открытой транзакции"


# ─────────────────────────── A9-P2-8(c): payment-control ───────────────────


async def _apartment_with_account(db) -> Apartment:
    yard = Yard(name="Двор P", is_active=True)
    db.add(yard)
    await db.flush()
    building = Building(address="ул. Платёжная 1", yard_id=yard.id, is_active=True,
                        entrance_count=1, floor_count=5)
    db.add(building)
    await db.flush()
    apt = Apartment(building_id=building.id, apartment_number="1", is_active=True,
                    account_number="770001")
    db.add(apt)
    await db.commit()
    await db.refresh(apt)
    return apt


async def test_payment_balance_http_without_open_tx(
    db_session, manager_user, recording_db, asgi_call, monkeypatch,
):
    from uk_management_bot.api.payment_control import router as module

    apt = await _apartment_with_account(db_session)
    _as_user(manager_user)
    tx: list[bool] = []

    async def fake_service(method, path, user, **kwargs):
        tx.append(recording_db.any_in_transaction())
        assert user.id == manager_user.id
        return {"status": "available", "current": {"debt": "1.00"}}

    monkeypatch.setattr(module, "service_request", fake_service)
    status, body = await asgi_call(
        "GET", f"/api/v2/payment-control/apartments/{apt.id}", [])

    assert status == 200 and body["status"] == "available"
    assert body["current"] == {"debt": "1.00"}
    assert tx == [False], "HTTP к сервису платежей шёл при открытой транзакции"


@pytest.mark.parametrize("payload", [{"unexpected": 1}, ["status"], None, {"current": {}}])
async def test_payment_balance_unexpected_format_is_not_500(
    db_session, manager_user, recording_db, asgi_call, monkeypatch, payload,
):
    """Неожиданный формат ответа сервиса = 502 «некорректный ответ»; для
    карточки квартиры он, как и прочие 502/503, отдаётся «unavailable» —
    а не KeyError/500."""
    from uk_management_bot.api.payment_control import router as module

    apt = await _apartment_with_account(db_session)
    _as_user(manager_user)
    monkeypatch.setattr(module, "service_request", AsyncMock(return_value=payload))

    status, body = await asgi_call(
        "GET", f"/api/v2/payment-control/apartments/{apt.id}", [])

    assert status == 200, body
    assert body["status"] == "unavailable" and body["current"] is None


async def test_balance_payload_validator_raises_502():
    from fastapi import HTTPException

    from uk_management_bot.api.payment_control.router import _balance_fields

    assert _balance_fields({"status": "no_data"}) == ("no_data", None)
    for bad in ({}, [], None, {"status": 5}):
        with pytest.raises(HTTPException) as exc:
            _balance_fields(bad)
        assert exc.value.status_code == 502
