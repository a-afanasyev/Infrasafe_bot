"""Пин-тесты этапа 2 аудита #10 (ревью внутренней защиты, 2026-10-24) — API.

A10-INT-06 — атрибуты auth-cookie (HttpOnly, SameSite=Strict, Path);
A10-INT-07 — resend OTP не возвращает исчерпанные попытки;
A10-INT-08 — /login сравнивает пароль и для неизвестного email (без тайминг-оракула).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from uk_management_bot.api.auth import router as auth_router
from uk_management_bot.api.auth import service as auth_service


def test_auth_cookies_are_httponly_strict_and_path_scoped():
    resp = Response()
    auth_router._set_auth_cookies(resp, "access", "refresh")

    cookies = resp.headers.getlist("set-cookie")
    assert len(cookies) == 2
    for raw in cookies:
        assert "HttpOnly" in raw
        assert "SameSite=strict" in raw
    assert any("Path=/uk/;" in c or c.endswith("Path=/uk/") for c in cookies)
    assert any("Path=/uk/api/" in c for c in cookies)


@pytest.mark.asyncio
async def test_store_otp_keeps_remaining_attempts():
    redis = MagicMock()
    redis.hset = AsyncMock()
    redis.hsetnx = AsyncMock()
    redis.expire = AsyncMock()
    redis.aclose = AsyncMock()
    with patch.object(auth_service, "_get_redis", AsyncMock(return_value=redis)):
        await auth_service.store_otp(42, "123456")

    redis.hset.assert_awaited_once_with("mfa:otp:42", "code", "123456")
    redis.hsetnx.assert_awaited_once_with("mfa:otp:42", "attempts", str(auth_service.MFA_MAX_ATTEMPTS))


def _request() -> Request:
    return Request({
        "type": "http", "method": "POST", "path": "/api/v2/auth/login",
        "headers": [], "query_string": b"", "client": ("127.0.0.1", 1),
    })


@pytest.mark.asyncio
async def test_login_runs_password_check_even_for_unknown_email():
    verify = MagicMock(return_value=False)
    with patch.object(auth_router, "user_by_email", AsyncMock(return_value=None)), patch.object(
        auth_router, "verify_password", verify
    ), patch.object(auth_router, "audit_login", AsyncMock()):
        with pytest.raises(HTTPException) as exc:
            await auth_router.login_password(
                _request(),
                auth_router.PasswordLogin(email="nobody@example.com", password="x" * 12),
                db=AsyncMock(),
            )

    assert exc.value.status_code == 401
    verify.assert_called_once_with("x" * 12, auth_service.DUMMY_PASSWORD_HASH)
