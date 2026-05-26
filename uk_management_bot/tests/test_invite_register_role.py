"""BUG-024 — registration must use `active_role` (or `roles` JSON), not
the legacy `user.role` column.

CLAUDE.md explicitly forbids `User.role` as the source-of-truth — `roles`
JSON + `active_role` is canonical. The pending-user re-registration path
in `web/api/invite.py` was reading `existing_user.role == "executor"` to
decide whether to attach a specialization, which lags behind on role
switches (e.g. user that moved from executor → manager but never updated
the legacy column).
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request

from uk_management_bot.web.limiter import web_limiter


@pytest.fixture(autouse=True)
def _reset_web_limiter():
    """Web-limiter quota is shared module-state — reset so prior tests'
    register hits don't pre-block our 3 calls."""
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


def _data(token: str = "valid-token", telegram_id: int = 555_000_010):
    from uk_management_bot.web.api.invite import RegistrationData
    return RegistrationData(
        token=token,
        full_name="Иван Петров",
        specialization="plumber",
        telegram_id=telegram_id,
    )


def _run(coro):
    return asyncio.run(coro)


def _existing_user(*, active_role: str | None, legacy_role: str, status: str = "pending"):
    """Build a User stand-in. The two fields can disagree on purpose —
    that's the whole point of the bug."""
    u = MagicMock()
    u.active_role = active_role
    u.role = legacy_role
    u.status = status
    u.telegram_id = 555_000_010
    u.id = 7
    return u


@pytest.mark.parametrize(
    "active_role,legacy_role,expected_specialization",
    [
        # active_role=executor wins, even if legacy says applicant.
        ("executor", "applicant", "plumber"),
        # active_role=manager → no specialization, regardless of legacy.
        ("manager", "executor", None),
        # active_role missing → fall back to legacy role.
        (None, "executor", "plumber"),
        (None, "applicant", None),
    ],
)
def test_specialization_follows_active_role_not_legacy(
    active_role, legacy_role, expected_specialization,
):
    """BUG-024: `specialization` is set only when the *active* role is
    executor. Pre-fix the code keyed off `existing_user.role`, which lags
    behind on role switches and corrupted profiles."""
    from uk_management_bot.web.api import invite as invite_module

    db = MagicMock()
    user = _existing_user(active_role=active_role, legacy_role=legacy_role)
    db.query.return_value.filter.return_value.first.return_value = user

    mock_invite = MagicMock()
    mock_invite.validate_invite.return_value = {
        "role": "applicant",  # token's role — irrelevant to this test
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
    assert user.specialization == expected_specialization, (
        f"active_role={active_role!r}, legacy role={legacy_role!r} → "
        f"expected specialization={expected_specialization!r}, "
        f"got {user.specialization!r}"
    )
