"""A9-P2-9: единый модуль отправки в Telegram (`api/telegram_send.py`).

Проверяется на уровне транспорта httpx общего клиента (фикстура
`telegram_api` из conftest), а не подменой модуля: каждое из шести мест
обязано реально пройти через модуль — иначе запрос не попадёт в заглушку.
"""
from __future__ import annotations

import logging

import httpx
import pytest

from uk_management_bot.api import telegram_send
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.user import User

pytestmark = pytest.mark.asyncio

FAKE_TOKEN = "7712345678:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
FAKE_SECRET = FAKE_TOKEN.split(":", 1)[1]
BLOCKED = {"description": "Forbidden: bot was blocked by the user"}


@pytest.fixture
def fake_token(monkeypatch):
    monkeypatch.setattr(settings, "BOT_TOKEN", FAKE_TOKEN)


@pytest.fixture
def side_db(monkeypatch, db_session_factory):
    """Отдельная async-сессия модуля (в sqlite-прогоне AsyncSessionLocal=None)."""
    from uk_management_bot.database import session as db_session_mod

    monkeypatch.setattr(db_session_mod, "AsyncSessionLocal", db_session_factory)


async def _user(db, tg: int, **extra) -> User:
    u = User(telegram_id=tg, first_name="Т", last_name=str(tg), roles='["applicant"]',
             active_role="applicant", status="approved", language="ru", **extra)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


# ═══════════════════════ Сам модуль ═══════════════════════


class TestModule:

    async def test_plain_text_sends_no_parse_mode(self, telegram_api, fake_token):
        telegram_api.reply(200, result={"message_id": 1})
        res = await telegram_send.send_message(5, "a < b & c")
        assert res.ok
        [body] = telegram_api.calls("sendMessage")
        assert body == {"chat_id": 5, "text": "a < b & c"}
        assert telegram_api.requests[0].url.path == f"/bot{FAKE_TOKEN}/sendMessage"

    async def test_client_is_reused(self, telegram_api, fake_token):
        telegram_api.reply(200, result={})
        await telegram_send.send_message(1, "x")
        first = telegram_send._client
        await telegram_send.send_message(2, "y")
        assert telegram_send._client is first

    @pytest.mark.parametrize("status,description,expected", [
        (200, "", "ok"),
        (403, "Forbidden: bot was blocked by the user", "blocked"),
        (403, "Forbidden: user is deactivated", "blocked"),
        (400, "Bad Request: chat not found", "no_chat"),
        (400, "Bad Request: message is too long", "error"),
        (429, "Too Many Requests", "error"),
        (500, "", "error"),
    ])
    async def test_classification(self, telegram_api, fake_token, status, description, expected):
        telegram_api.reply(status, description=description)
        assert (await telegram_send.send_message(1, "x", mark_blocked=False)).status == expected

    async def test_non_json_5xx_is_error(self, telegram_api, fake_token):
        telegram_api.handler = lambda r: httpx.Response(502, text="<html>bad gateway</html>")
        res = await telegram_send.send_message(1, "x")
        assert res.status == "error" and res.http_status == 502

    async def test_blocked_stamps_user_in_separate_session(
        self, telegram_api, fake_token, side_db, db_session,
    ):
        user = await _user(db_session, 4201)
        telegram_api.reply(403, **BLOCKED)

        res = await telegram_send.send_message(4201, "x")

        assert res.status == "blocked"
        await db_session.refresh(user)
        assert user.bot_blocked_at is not None

    async def test_blocked_without_mark_leaves_user(
        self, telegram_api, fake_token, side_db, db_session,
    ):
        user = await _user(db_session, 4202)
        telegram_api.reply(403, **BLOCKED)
        await telegram_send.send_message(4202, "x", mark_blocked=False)
        await db_session.refresh(user)
        assert user.bot_blocked_at is None

    async def test_other_errors_do_not_stamp(self, telegram_api, fake_token, side_db, db_session):
        user = await _user(db_session, 4203)
        telegram_api.reply(500)
        await telegram_send.send_message(4203, "x")
        await db_session.refresh(user)
        assert user.bot_blocked_at is None

    async def test_connect_failure_retried_once(self, telegram_api, fake_token):
        attempts = []

        def handler(request):
            attempts.append(1)
            if len(attempts) == 1:
                raise httpx.ConnectTimeout("boom", request=request)
            return httpx.Response(200, json={"ok": True, "result": {}})

        telegram_api.handler = handler
        assert (await telegram_send.send_message(1, "x")).ok
        assert len(attempts) == 2

    async def test_two_connect_failures_are_error(self, telegram_api, fake_token):
        def handler(request):
            raise httpx.ConnectError("boom", request=request)

        telegram_api.handler = handler
        res = await telegram_send.send_message(1, "x")
        assert res.status == "error"
        assert len(telegram_api.requests) == 2

    async def test_read_timeout_not_retried(self, telegram_api, fake_token):
        def handler(request):
            raise httpx.ReadTimeout("boom", request=request)

        telegram_api.handler = handler
        assert (await telegram_send.send_message(1, "x")).status == "error"
        assert len(telegram_api.requests) == 1

    async def test_token_never_logged(self, telegram_api, fake_token, caplog):
        def handler(request):
            raise httpx.ReadTimeout(f"timed out for url {request.url}", request=request)

        telegram_api.handler = handler
        with caplog.at_level(logging.DEBUG):
            await telegram_send.send_message(1, "x")
            await telegram_send.get_me()
        assert FAKE_SECRET not in caplog.text
        assert "ReadTimeout" in caplog.text

    async def test_download_too_large_and_unavailable(self, telegram_api, fake_token):
        telegram_api.handler = lambda r: httpx.Response(200, content=b"x" * 11)
        with pytest.raises(telegram_send.TelegramFileTooLarge):
            await telegram_send.download_file("a/b.jpg", max_bytes=10)
        assert telegram_api.requests[-1].url.path == f"/file/bot{FAKE_TOKEN}/a/b.jpg"

        telegram_api.handler = lambda r: httpx.Response(500)
        with pytest.raises(telegram_send.TelegramUnavailable) as ei:
            await telegram_send.download_file("a/b.jpg", max_bytes=10)
        assert FAKE_SECRET not in str(ei.value)


# ═══════════════════════ Шесть мест вызова ═══════════════════════


class TestOtp:
    """`api/auth/service.send_otp_via_bot` + вход по паролю (MFA)."""

    async def test_otp_goes_through_module_as_html(self, telegram_api, fake_token):
        from uk_management_bot.api.auth.service import send_otp_via_bot

        telegram_api.reply(200, result={})
        assert await send_otp_via_bot(4301, "123456") is True
        [body] = telegram_api.calls("sendMessage")
        assert body["chat_id"] == 4301
        assert body["parse_mode"] == "HTML"
        assert "<b>123456</b>" in body["text"]

    @pytest.mark.parametrize("handler", [
        lambda r: httpx.Response(500, json={"ok": False, "description": "x"}),
        lambda r: httpx.Response(403, json={"ok": False, **BLOCKED}),
    ])
    async def test_otp_refusal_is_false(self, telegram_api, fake_token, handler):
        from uk_management_bot.api.auth.service import send_otp_via_bot

        telegram_api.handler = handler
        assert await send_otp_via_bot(4302, "123456") is False

    async def test_otp_network_down_is_false_without_token_in_log(
        self, telegram_api, fake_token, caplog,
    ):
        from uk_management_bot.api.auth.service import send_otp_via_bot

        def handler(request):
            raise httpx.ConnectError(f"boom {request.url}", request=request)

        telegram_api.handler = handler
        with caplog.at_level(logging.DEBUG):
            assert await send_otp_via_bot(4303, "123456") is False
        assert FAKE_SECRET not in caplog.text

    async def _login(self, client, db_session, monkeypatch):
        from uk_management_bot.api.auth import router as auth_router
        from uk_management_bot.api.auth.service import hash_password

        await _user(db_session, 4304, email="otp@example.com",
                    password_hash=hash_password("Secret-pass-123"))

        async def _store(user_id, code):  # Redis — не предмет теста
            return None

        monkeypatch.setattr(auth_router, "store_otp", _store)
        return await client.post("/api/v2/auth/login",
                                 json={"email": "otp@example.com", "password": "Secret-pass-123"})

    async def test_login_telegram_down_is_503(
        self, client, db_session, telegram_api, fake_token, monkeypatch,
    ):
        def handler(request):
            raise httpx.ConnectTimeout("down", request=request)

        telegram_api.handler = handler
        r = await self._login(client, db_session, monkeypatch)
        assert r.status_code == 503
        assert r.json()["detail"] == "Failed to send verification code. Try again later."

    async def test_login_ok_returns_mfa_token(
        self, client, db_session, telegram_api, fake_token, monkeypatch,
    ):
        telegram_api.reply(200, result={})
        r = await self._login(client, db_session, monkeypatch)
        assert r.status_code == 200
        assert r.json()["mfa_required"] is True
        assert len(telegram_api.calls("sendMessage")) == 1


class TestRegistrationNotify:

    async def test_plain_text_to_each_admin(self, telegram_api, fake_token, monkeypatch):
        from uk_management_bot.api.registration.notify import notify_managers_new_registration

        monkeypatch.setattr(settings, "ADMIN_USER_IDS", [11, 12])
        telegram_api.reply(200, result={})
        delivered = await notify_managers_new_registration(
            telegram_id=5, full_name="Иван <Ко>", apartment_label="Двор-1 & кв 12")
        bodies = telegram_api.calls("sendMessage")
        assert [b["chat_id"] for b in bodies] == [11, 12]
        assert all("parse_mode" not in b for b in bodies)
        assert "Иван <Ко>" in bodies[0]["text"]
        assert delivered == 2

    async def test_non_2xx_is_reported_not_success(
        self, telegram_api, fake_token, monkeypatch, caplog,
    ):
        """Раньше статус ответа не проверялся — недоставка выглядела успехом."""
        from uk_management_bot.api.registration.notify import notify_managers_new_registration

        monkeypatch.setattr(settings, "ADMIN_USER_IDS", [11])
        telegram_api.reply(400, description="Bad Request: chat not found")
        with caplog.at_level(logging.WARNING):
            delivered = await notify_managers_new_registration(
                telegram_id=5, full_name="Иван", apartment_label="кв 1")
        assert delivered == 0
        assert "не доставлено" in caplog.text


class TestResidentsNotify:

    async def test_decision_notice_is_plain_text(self, telegram_api, fake_token, db_session):
        from uk_management_bot.api.residents import notify

        resident = await _user(db_session, 4401)
        telegram_api.reply(200, result={})
        await notify.notify_binding_approved(resident, "ул. <А> & Б")
        [body] = telegram_api.calls("sendMessage")
        assert body["chat_id"] == 4401
        assert "parse_mode" not in body
        assert "ул. <А> & Б" in body["text"]

    async def test_blocked_resident_is_stamped(
        self, telegram_api, fake_token, side_db, db_session,
    ):
        from uk_management_bot.api.residents import notify

        resident = await _user(db_session, 4402)
        telegram_api.reply(403, **BLOCKED)
        await notify.notify_verification_approved(resident)  # не поднимает
        await db_session.refresh(resident)
        assert resident.bot_blocked_at is not None

    async def test_plain_messages_default_html_and_count(self, telegram_api, fake_token):
        from uk_management_bot.api.residents import notify
        from uk_management_bot.services.elevator_service import Message

        telegram_api.handler = lambda r: (
            httpx.Response(403, json={"ok": False, **BLOCKED})
            if b'"chat_id":2' in r.content.replace(b" ", b"")
            else httpx.Response(200, json={"ok": True, "result": {}}))
        delivered = await notify.send_plain_messages(
            [Message(telegram_id=i, text="t") for i in (1, 2, 3)])
        assert delivered == 2
        assert all(b["parse_mode"] == "HTML" for b in telegram_api.calls("sendMessage"))


class TestPhoneRequest:

    async def test_endpoint_sends_contact_keyboard(
        self, client, db_session, telegram_api, fake_token,
    ):
        emp = await _user(db_session, 4501)
        telegram_api.reply(200, result={})
        r = await client.post(f"/api/v2/shifts/employees/{emp.id}/request-phone")
        assert r.status_code == 200
        [body] = telegram_api.calls("sendMessage")
        assert body["chat_id"] == 4501
        assert "parse_mode" not in body
        rows = body["reply_markup"]["keyboard"]
        assert any(b.get("request_contact") is True for row in rows for b in row)

    async def test_blocked_is_409_and_stamped(
        self, client, db_session, telegram_api, fake_token, side_db,
    ):
        emp = await _user(db_session, 4502)
        telegram_api.reply(403, **BLOCKED)
        r = await client.post(f"/api/v2/shifts/employees/{emp.id}/request-phone")
        assert r.status_code == 409
        await db_session.refresh(emp)
        assert emp.bot_blocked_at is not None

    async def test_network_down_is_502(self, client, db_session, telegram_api, fake_token):
        emp = await _user(db_session, 4503)

        def handler(request):
            raise httpx.ConnectTimeout("down", request=request)

        telegram_api.handler = handler
        r = await client.post(f"/api/v2/shifts/employees/{emp.id}/request-phone")
        assert r.status_code == 502
        assert len(telegram_api.requests) == 2  # один ретрай connect-сбоя


class TestInviteUsername:

    async def test_getme_goes_through_module(self, telegram_api, fake_token, monkeypatch):
        from uk_management_bot.api.shifts.router import _helpers

        monkeypatch.setattr(settings, "BOT_USERNAME", None)
        telegram_api.reply(200, result={"username": "infrasafebot"})
        assert await _helpers._resolve_bot_username() == "infrasafebot"
        assert telegram_api.requests[0].url.path.endswith("/getMe")
