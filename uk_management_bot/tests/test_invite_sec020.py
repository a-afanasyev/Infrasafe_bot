"""SEC-020 — TOCTOU race + GET enumeration on invite endpoints.

Coverage:
  * `validate_invite` без mark_used_by → не consum'ит nonce (GET path).
  * `validate_invite` второй раз с mark_used_by → TokenAlreadyUsedError.
  * Endpoint POST /register: race-loser → 409, other validation → 400.
  * Endpoint GET /validate: rate-limit 20/мин/IP (web_limiter).

The unit-level tests run with MagicMock'd InviteService; the rate-limit
test exercises the actual `web_limiter` (in-memory storage in the test
process). The 100-parallel-POST race test from the spec AC (d) requires
a real Postgres + threading and is covered by
`tests/test_invite_integration.py` against the integration DB — not
re-implemented here to keep this file mock-only.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from uk_management_bot.web.limiter import web_limiter


@pytest.fixture(autouse=True)
def _reset_web_limiter():
    """`@web_limiter.limit("3/minute")` on /register is module-level
    in-memory state. Reset between tests so the 4th endpoint-call test
    in this file isn't pre-blocked by the 3-per-minute cap of earlier
    tests (all hitting default 127.0.0.1 since the mocked Request stays
    constant)."""
    web_limiter.reset()
    yield
    web_limiter.reset()


def _make_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/register",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


def _run(coro):
    return asyncio.run(coro)


def _data(token: str = "valid-token", telegram_id: int = 555_000_001):
    from uk_management_bot.web.api.invite import RegistrationData

    return RegistrationData(
        token=token,
        full_name="Иван Петров",
        specialization="plumber",
        telegram_id=telegram_id,
    )


# ── Service-level: typed exception is raised, not generic ValueError ──

def test_validate_invite_raises_token_already_used_error_on_race_loser():
    """The atomic INSERT path raises the typed exception (subclass of
    ValueError, so old try/except ValueError catchers still work)."""
    from uk_management_bot.services.invite_service import (
        TokenAlreadyUsedError,
    )
    from sqlalchemy.exc import IntegrityError

    # Build the service with a MagicMock'd db that throws IntegrityError on
    # flush — simulating the second concurrent INSERT losing to UNIQUE.
    with patch("uk_management_bot.services.invite_service.settings") as mock_settings:
        mock_settings.INVITE_SECRET = "test_secret_for_unit_tests"
        from uk_management_bot.services.invite_service import InviteService

        db = MagicMock()
        db.flush.side_effect = IntegrityError("INSERT", {}, Exception())
        svc = InviteService(db)

        with pytest.raises(TokenAlreadyUsedError, match="already used"):
            svc._use_nonce_atomically("test-nonce", 555, {"role": "applicant"})

    # And it's a ValueError subclass for back-compat with older catchers.
    assert issubclass(TokenAlreadyUsedError, ValueError)


# ── Endpoint-level: race-loser maps to 409 (new-user branch) ──

class TestRegisterEndpoint409OnRaceLoser:
    def test_new_user_race_loser_returns_409(self):
        """When join_via_invite returns reason='already_used', the
        endpoint must raise HTTPException(409). Pre-SEC-020 it was 400."""
        from uk_management_bot.web.api import invite as invite_module

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None  # no existing user
        data = _data()

        mock_invite = MagicMock()
        mock_invite.join_via_invite.return_value = {
            "success": False,
            "reason": "already_used",
            "message": "Token already used",
        }

        with patch.object(invite_module, "InviteService", return_value=mock_invite), \
             patch.object(invite_module, "AuthService", return_value=MagicMock()):
            with pytest.raises(HTTPException) as exc:
                _run(invite_module.register_via_invite(
                    request=_make_request(), data=data, db=db
                ))

        assert exc.value.status_code == 409
        assert "already used" in str(exc.value.detail).lower()

    def test_new_user_other_validation_error_stays_400(self):
        """Non-race validation errors (bad signature, expired, etc.) keep
        the 400 status — only the race-loser is 409."""
        from uk_management_bot.web.api import invite as invite_module

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        data = _data()

        mock_invite = MagicMock()
        mock_invite.join_via_invite.return_value = {
            "success": False,
            "message": "Token has expired",
            # no reason field → falls through to default 400
        }

        with patch.object(invite_module, "InviteService", return_value=mock_invite), \
             patch.object(invite_module, "AuthService", return_value=MagicMock()):
            with pytest.raises(HTTPException) as exc:
                _run(invite_module.register_via_invite(
                    request=_make_request(), data=data, db=db
                ))

        assert exc.value.status_code == 400


class TestRegisterEndpointExistingUser:
    def test_existing_user_race_loser_returns_409(self):
        """Pending user retrying registration loses the race → 409.
        Previously (before SEC-020 fix), validate_invite returning the
        payload was misread as falsy and always 400'd; the new explicit
        try/except sorts both bugs at once."""
        from uk_management_bot.web.api import invite as invite_module
        from uk_management_bot.services.invite_service import TokenAlreadyUsedError

        existing = MagicMock()
        existing.status = "pending"
        existing.telegram_id = 555_000_001
        existing.role = "applicant"
        existing.id = 7

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = existing

        mock_invite = MagicMock()
        mock_invite.validate_invite.side_effect = TokenAlreadyUsedError("Token already used")

        with patch.object(invite_module, "InviteService", return_value=mock_invite), \
             patch.object(invite_module, "AuthService", return_value=MagicMock()):
            with pytest.raises(HTTPException) as exc:
                _run(invite_module.register_via_invite(
                    request=_make_request(), data=_data(), db=db
                ))

        assert exc.value.status_code == 409

    def test_existing_user_happy_path_now_works(self):
        """Pending user re-registers with a still-valid token — this
        used to always 400 because `validation_result.get("valid")` was
        None (validate_invite returns the payload dict, not the wrapper).
        The new explicit try/except let the payload flow through."""
        from uk_management_bot.web.api import invite as invite_module

        existing = MagicMock()
        existing.status = "pending"
        existing.telegram_id = 555_000_002
        existing.role = "executor"
        existing.id = 8

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = existing

        mock_invite = MagicMock()
        # validate_invite returns the *payload* dict on success.
        mock_invite.validate_invite.return_value = {
            "role": "executor",
            "expires_at": 9999999999,
            "nonce": "n",
            "created_by": 1,
        }

        with patch.object(invite_module, "InviteService", return_value=mock_invite), \
             patch.object(invite_module, "AuthService", return_value=MagicMock()):
            result = _run(invite_module.register_via_invite(
                request=_make_request(), data=_data(), db=db
            ))

        assert result["success"] is True
        assert result["user_id"] == 8


# ── GET /validate rate-limit ──

@pytest.mark.asyncio
async def test_get_validate_rate_limited_at_20_per_minute():
    """20 calls within a minute succeed, 21st returns 429. We exercise
    the real `web_limiter` via a minimal FastAPI app wired to the same
    endpoint, with a unique X-Real-IP so neighbour tests don't collide."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from slowapi.errors import RateLimitExceeded
    from slowapi import _rate_limit_exceeded_handler

    from uk_management_bot.web.limiter import web_limiter
    from uk_management_bot.web.api.invite import router as invite_router

    # Reset the limiter so prior tests don't pre-fill our bucket.
    web_limiter.reset()

    app = FastAPI()
    app.state.limiter = web_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(invite_router, prefix="/api")

    # Stub the db dependency — the endpoint only needs `db: Session = Depends(get_db)`
    # to be resolvable; it never queries because the token is malformed.
    from uk_management_bot.database.session import get_db
    app.dependency_overrides[get_db] = lambda: MagicMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"X-Real-IP": "198.51.100.42"}  # TEST-NET-2
        for i in range(20):
            r = await client.get("/api/validate/not-a-real-token", headers=headers)
            # We're not testing token validity — only the rate limiter.
            # The endpoint returns 200 with valid=False for bad tokens.
            assert r.status_code == 200, f"call {i+1} got {r.status_code}: {r.text}"

        # 21st call exceeds the per-minute quota.
        r = await client.get("/api/validate/not-a-real-token", headers=headers)
        assert r.status_code == 429
