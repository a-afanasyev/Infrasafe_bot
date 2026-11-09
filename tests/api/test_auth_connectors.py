"""Auth-коннекторы: негативные тесты (ревью 2026-11-07,
docs/audit/auth-connectors-review-2026-11-07.md, часть B).

Секреты здесь только фейковые: bot token — строка-заглушка, JWT/вебхук-ключи —
CI-значения окружения тестов.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
import uuid
from unittest.mock import AsyncMock
from urllib.parse import urlencode

import pytest
import redis.asyncio as aioredis
from sqlalchemy import select

import uk_management_bot.api.auth.router as auth_router
from uk_management_bot.api.auth import service as auth_service
from uk_management_bot.api.auth.service import (
    create_access_token, hash_token, save_refresh_token, verify_telegram_widget,
    verify_twa_init_data,
)
from uk_management_bot.api.dependencies import get_current_user
from uk_management_bot.api.main import app
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.refresh_token import RefreshToken

FAKE_BOT_TOKEN = "123456:FAKE-TOKEN-FOR-TESTS"


# ── 1. TWA initData ─────────────────────────────────────────────────────


def _init_data(bot_token: str = FAKE_BOT_TOKEN, *, auth_date: int | None = None,
               drop_auth_date: bool = False, **extra) -> str:
    fields = {"user": json.dumps({"id": 4242, "first_name": "T"}), "query_id": "Q1", **extra}
    if not drop_auth_date:
        fields["auth_date"] = str(auth_date if auth_date is not None else int(time.time()))
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.digest(b"WebAppData", bot_token.encode(), "sha256")
    fields["hash"] = hmac.digest(secret, dcs.encode(), "sha256").hex()
    return urlencode(fields)


def test_init_data_valid_is_accepted():
    assert verify_twa_init_data(_init_data(), FAKE_BOT_TOKEN)["id"] == 4242


@pytest.mark.parametrize("bad", [
    _init_data(bot_token="999:OTHER-BOT"),                                       # чужой бот
    _init_data(auth_date=int(time.time()) - auth_service.AUTH_DATE_MAX_AGE_SECONDS - 5),  # протух
    _init_data(drop_auth_date=True),                                             # без auth_date
    _init_data().replace("Q1", "Q2"),                                            # подмена поля
])
def test_init_data_rejected(bad):
    assert verify_twa_init_data(bad, FAKE_BOT_TOKEN) is None


def test_init_data_window_is_explicit_five_minutes():
    assert auth_service.AUTH_DATE_MAX_AGE_SECONDS == 300


# ── 2. Login Widget ─────────────────────────────────────────────────────


def _widget(bot_token: str, **over) -> dict:
    data = {"id": 4242, "first_name": "T", "auth_date": int(time.time()), **over}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    key = hashlib.sha256(bot_token.encode()).digest()
    return {**data, "hash": hmac.digest(key, dcs.encode(), "sha256").hex()}


def test_widget_signed_with_sha256_of_bot_token(monkeypatch):
    monkeypatch.setattr(settings, "BOT_TOKEN", FAKE_BOT_TOKEN)
    assert verify_telegram_widget(_widget(FAKE_BOT_TOKEN)) is True
    assert verify_telegram_widget(_widget("999:OTHER-BOT")) is False
    stale = _widget(FAKE_BOT_TOKEN, auth_date=int(time.time()) - 301)
    assert verify_telegram_widget(stale) is False


# ── 3. OTP ──────────────────────────────────────────────────────────────


async def _redis_or_skip():
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await r.ping()
    except Exception:  # noqa: BLE001
        await r.aclose()
        pytest.skip("нужен настоящий Redis (make test-ci поднимает его)")
    return r


@pytest.mark.asyncio
async def test_otp_resend_after_lockout_does_not_refill_attempts():
    """A10-INT-07: исчерпание попыток не обнуляется повторной отправкой кода.

    Было: исчерпание удаляло ключ, и resend выдавал три свежие попытки — перебор
    второго фактора шёл без конца, по 3 кода на каждый resend.
    """
    r = await _redis_or_skip()
    uid = 910_000_000 + uuid.uuid4().int % 1_000_000
    try:
        await auth_service.store_otp(uid, "111111")
        for _ in range(auth_service.MFA_MAX_ATTEMPTS):
            await auth_service.verify_otp(uid, "000000")
        with pytest.raises(auth_service.OtpLocked):          # resend во время блока
            await auth_service.store_otp(uid, "222222")
        ok, msg = await auth_service.verify_otp(uid, "222222")
        assert ok is False
    finally:
        await r.delete(f"mfa:otp:{uid}")
        await r.aclose()


@pytest.mark.asyncio
async def test_otp_lockout_is_not_extended_by_resend():
    """Ревью PR #718: resend во время блока не продлевает TTL и не кладёт мёртвый код —
    иначе знающий пароль держал бы блок бесконечно, а «через 5 минут» врало."""
    r = await _redis_or_skip()
    uid = 930_000_000 + uuid.uuid4().int % 1_000_000
    key = f"mfa:otp:{uid}"
    try:
        await auth_service.store_otp(uid, "111111")
        for _ in range(auth_service.MFA_MAX_ATTEMPTS):
            await auth_service.verify_otp(uid, "000000")
        await r.expire(key, 100)
        with pytest.raises(auth_service.OtpLocked):
            await auth_service.store_otp(uid, "222222")
        assert await r.ttl(key) <= 100
        assert await r.hget(key, "code") is None
    finally:
        await r.delete(key)
        await r.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v2/auth/login", "/api/v2/auth/login/resend-otp"])
async def test_locked_otp_answers_429_without_sending(path, client, db_session, manager_user, monkeypatch):
    manager_user.email, manager_user.password_hash = "lock@test", auth_service.hash_password("pw-123456")
    db_session.add(manager_user)
    await db_session.commit()
    monkeypatch.setattr(auth_router, "store_otp", AsyncMock(side_effect=auth_service.OtpLocked))
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(auth_router, "send_otp_via_bot", send)
    body = ({"email": "lock@test", "password": "pw-123456"} if path.endswith("login")
            else {"mfa_token": auth_service.create_mfa_token(manager_user.id)})
    resp = await client.post(path, json=body)
    assert resp.status_code == 429, resp.text
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_login_never_returns_or_logs_the_code(client, db_session, manager_user, monkeypatch, caplog):
    manager_user.email, manager_user.password_hash = "m@test", auth_service.hash_password("pw-123456")
    db_session.add(manager_user)
    await db_session.commit()
    sent = {}
    monkeypatch.setattr(auth_router, "store_otp", AsyncMock())

    async def _send(tg, code):
        sent["code"] = code
        return True

    monkeypatch.setattr(auth_router, "send_otp_via_bot", _send)
    resp = await client.post("/api/v2/auth/login", json={"email": "m@test", "password": "pw-123456"})
    assert resp.status_code == 200, resp.text
    assert sent["code"] not in resp.text
    assert sent["code"] not in caplog.text


@pytest.mark.asyncio
async def test_login_same_answer_for_unknown_and_wrong_password(client, db_session, manager_user):
    manager_user.email, manager_user.password_hash = "m2@test", auth_service.hash_password("pw-123456")
    db_session.add(manager_user)
    await db_session.commit()
    unknown = await client.post("/api/v2/auth/login", json={"email": "nobody@test", "password": "x" * 8})
    wrong = await client.post("/api/v2/auth/login", json={"email": "m2@test", "password": "x" * 8})
    assert (unknown.status_code, unknown.json()) == (wrong.status_code, wrong.json()) == (
        401, {"detail": "Invalid credentials"})


def test_all_otp_routes_are_behind_auth_ratelimit_guard():
    from fastapi.routing import APIRoute

    from uk_management_bot.api.rate_limit import auth_ratelimit_guard

    def calls(dep):
        for d in dep.dependencies:
            yield d.call
            yield from calls(d)

    paths = {"/api/v2/auth/login", "/api/v2/auth/login/verify-otp", "/api/v2/auth/login/resend-otp"}
    guarded = {r.path for r in app.routes if isinstance(r, APIRoute) and r.path in paths
               and auth_ratelimit_guard in set(calls(r.dependant))}
    assert guarded == paths


# ── 4. Refresh-токены: блокировка отзывает сразу ────────────────────────


@pytest.mark.asyncio
async def test_blocking_user_revokes_refresh_tokens(db_session, manager_user, resident_user):
    """Блокировка отзывает refresh-сессии: после разблокировки старые не оживают."""
    from uk_management_bot.services.users.status import set_user_status

    await save_refresh_token(db_session, resident_user.id, "old-refresh-value")
    await set_user_status(db_session, resident_user, "blocked")
    row = (await db_session.execute(select(RefreshToken).where(
        RefreshToken.token_hash == hash_token("old-refresh-value")))).scalar_one()
    assert row.revoked_at is not None


# ── 5. Тикет регистрации: один активный на аккаунт ──────────────────────


@pytest.mark.asyncio
async def test_registration_ticket_reissue_and_completion_revoke():
    from uk_management_bot.api.registration import tickets

    r = await _redis_or_skip()
    tid = 920_000_000 + uuid.uuid4().int % 1_000_000
    try:
        first = await tickets.issue_registration_ticket(tid)
        assert await tickets.check_registration_ticket(first) == tid
        second = await tickets.issue_registration_ticket(tid)
        assert await tickets.check_registration_ticket(first) is None   # перевыпуск гасит старый
        assert await tickets.check_registration_ticket(second) == tid
        await tickets.revoke_registration_tickets(tid)                  # регистрация завершена
        assert await tickets.check_registration_ticket(second) is None
    finally:
        await r.delete(f"reg:ticket:{tid}")
        await r.aclose()


@pytest.mark.asyncio
async def test_registration_ticket_marker_is_fail_open(monkeypatch):
    """Ревью PR #718: без Redis /start и завершение регистрации не дают 500."""
    from uk_management_bot.api.registration import tickets

    monkeypatch.setattr(tickets, "_get_redis", AsyncMock(side_effect=ConnectionError("down")))
    token = await tickets.issue_registration_ticket(4242)
    assert tickets.verify_registration_ticket(token) == 4242
    await tickets.revoke_registration_tickets(4242)   # не бросает


# ── 8. CSRF для cookie-сессии ───────────────────────────────────────────

URL = "/api/v2/requests/260101-999/remind-applicant"   # мутирующая ручка менеджера, без тела


@pytest.fixture
def cookie_client(client, manager_user):
    app.dependency_overrides.pop(get_current_user, None)   # настоящая cookie-аутентификация
    client.cookies.set("uk_access", create_access_token(manager_user.id, ["manager"]))
    yield client
    client.cookies.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [
    {"Content-Type": "application/x-www-form-urlencoded"},                         # без Origin — не браузер, но форма
    {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site",
     "Content-Type": "application/x-www-form-urlencoded"},
    {"Origin": "https://sub.example", "Sec-Fetch-Site": "same-site",
     "Content-Type": "text/plain"},
])
async def test_cookie_mutation_from_foreign_origin_is_rejected(cookie_client, headers):
    resp = await cookie_client.post(URL, content=b"a=1", headers=headers)
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "csrf_rejected"


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [
    {"Sec-Fetch-Site": "same-origin", "Content-Type": "application/x-www-form-urlencoded"},
    {"Origin": "http://localhost:5173", "Content-Type": "multipart/form-data; boundary=x"},
    {"Content-Type": "application/json"},
])
async def test_cookie_mutation_from_own_origin_passes(cookie_client, headers):
    resp = await cookie_client.post(URL, content=b"{}" if "json" in headers["Content-Type"] else b"",
                                    headers=headers)
    assert resp.status_code == 404, resp.text   # дошли до хендлера: заявки нет


@pytest.mark.asyncio
async def test_bearer_is_not_subject_to_csrf(client, manager_user):
    app.dependency_overrides.pop(get_current_user, None)
    resp = await client.post(URL, headers={
        "Authorization": f"Bearer {create_access_token(manager_user.id, ['manager'])}",
        "Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"})
    assert resp.status_code == 404, resp.text


# ── 10. Ключ media-service не уходит клиенту ────────────────────────────


@pytest.mark.asyncio
async def test_media_key_rejection_is_not_echoed(client, monkeypatch):
    import uk_management_bot.api.routes.media_proxy as media_proxy

    monkeypatch.setattr(settings, "MEDIA_SERVICE_URL", "http://media.test")
    monkeypatch.setattr(settings, "MEDIA_SERVICE_API_KEY", "fake-media-key-should-not-leak")
    monkeypatch.setattr(media_proxy, "check_request_access", AsyncMock())

    async def _get(client_, url, **kw):
        import httpx
        return httpx.Response(401, json={"detail": "bad key", "key": kw.get("headers")},
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(media_proxy, "get_with_retries", _get)
    resp = await client.get("/api/v2/media/request/260101-001")
    assert resp.status_code == 502
    assert "fake-media-key" not in resp.text and not re.search(r"x-api-key", resp.text, re.I)
