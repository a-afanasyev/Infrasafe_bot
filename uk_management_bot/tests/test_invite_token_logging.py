"""
FIX-006 — Ensure invite tokens are masked in auth logs.

The handler `join_with_invite` previously emitted the full invite token to
the bot logs (`logger.info(...{token}...)`). Anyone with access to
`docker logs uk-management-bot` could pick that token up and register as
the invited user. The token MUST be masked: only a short prefix may be
logged (≤ 8 chars + ellipsis), never the full token body.

Test contract:
- Capture the logger of `uk_management_bot.handlers.auth`.
- Invoke `join_with_invite` with a stub token whose body is ≥ 20 chars.
- Assert the captured log NEVER contains the full token body.
- Assert it DOES contain the `invite_v1:` prefix (masked form).
"""
import logging
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from aiogram.types import Message, User as TgUser
from sqlalchemy.orm import Session


# Stub token with a clearly identifiable body. The body length is well
# above 20 chars so the un-masked leak is unambiguous.
TOKEN_BODY = "ABCDEFGH123456789012345"
STUB_TOKEN = f"invite_v1:{TOKEN_BODY}"


def _make_tg_user(user_id: int = 42) -> MagicMock:
    u = MagicMock(spec=TgUser)
    u.id = user_id
    u.username = "tester"
    u.first_name = "Test"
    u.last_name = "User"
    return u


def _make_message(text: str, user_id: int = 42) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = _make_tg_user(user_id=user_id)
    msg.text = text
    msg.answer = AsyncMock()
    return msg


def _make_state() -> MagicMock:
    state = MagicMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.get_state = AsyncMock(return_value="RegistrationStates:waiting_for_full_name")
    return state


def _make_db() -> MagicMock:
    return MagicMock(spec=Session)


@pytest.mark.asyncio
async def test_join_handler_masks_token_in_log(caplog):
    """`/join <token>` MUST NOT log the full invite token body.

    FIX-006 scope: only the "получил ссылку на веб-регистрацию" log line at
    handlers/auth.py:172. The bare-`message.text` echo at the top of the
    same handler is a separate leak tracked under REFACTOR-032; we filter
    it out here to keep this test focused on FIX-006.
    """
    from uk_management_bot.handlers.auth import join_with_invite

    # Stub the rate limiter so it always allows the call through.
    rate_limiter_ok = AsyncMock(return_value=True)

    # Stub the invite service so it returns a valid payload without
    # touching the database or HMAC machinery.
    fake_invite_data = {
        "role": "applicant",
        "specialization": "",
        "expires_at": 9_999_999_999,
        "created_by": 1,
        "nonce": "abc123",
    }

    fake_invite_service_instance = MagicMock()
    fake_invite_service_instance.validate_invite.return_value = fake_invite_data

    # Stub AuthService: no existing user → registration is allowed.
    fake_auth_service_instance = MagicMock()
    fake_auth_service_instance.get_user_by_telegram_id = AsyncMock(return_value=None)

    msg = _make_message(f"/join {STUB_TOKEN}", user_id=42)
    state = _make_state()
    db = _make_db()

    with caplog.at_level(logging.INFO, logger="uk_management_bot.handlers.auth"), \
        patch(
            "uk_management_bot.handlers.auth.InviteRateLimiter.is_allowed",
            new=rate_limiter_ok,
        ), \
        patch(
            "uk_management_bot.handlers.auth.InviteService",
            return_value=fake_invite_service_instance,
        ), \
        patch(
            "uk_management_bot.handlers.auth.AuthService",
            return_value=fake_auth_service_instance,
        ), \
        patch(
            "uk_management_bot.handlers.auth.get_text",
            side_effect=lambda key, language="ru", **kw: f"<text:{key}>",
        ):
        await join_with_invite(msg, state, db, language="ru")

    # Locate ONLY the FIX-006 target log message — the "received web
    # registration link" line at auth.py:172. Other log lines in this
    # handler that may carry the token (e.g. echoing message.text at
    # entry) are out of scope here; REFACTOR-032 covers them.
    target_records = [
        rec for rec in caplog.records
        if rec.name == "uk_management_bot.handlers.auth"
        and "получил ссылку на веб-регистрацию" in rec.getMessage()
    ]

    assert target_records, (
        "Expected the 'получил ссылку на веб-регистрацию' log line to be "
        "emitted by join_with_invite, but it was not captured."
    )

    target_text = "\n".join(rec.getMessage() for rec in target_records)

    # The full token body MUST NOT appear in the target log line.
    assert TOKEN_BODY not in target_text, (
        f"Full invite token body leaked in FIX-006 log line: {target_text!r}"
    )
    assert STUB_TOKEN not in target_text, (
        f"Full invite token leaked in FIX-006 log line: {target_text!r}"
    )

    # A masked reference should still be present so operators can
    # correlate logs with a token without recovering it. `token[:8]` of
    # "invite_v1:ABC..." is the 8-char prefix "invite_v" followed by an
    # ellipsis.
    assert "invite_v" in target_text, (
        f"Expected masked invite_v prefix in FIX-006 log line but got: {target_text!r}"
    )
    assert "…" in target_text, (
        f"Expected ellipsis marking truncation in FIX-006 log line but got: {target_text!r}"
    )


@pytest.mark.asyncio
async def test_join_handler_no_full_token_in_any_log(caplog):
    """AC-level check: NO log record from join_with_invite handler may
    contain the full invite token body. This covers ALL log lines in the
    handler (entry "Команда /join", exit "получил ссылку"), enforcing the
    backlog AC: `docker logs ... | grep -E "invite_v1:[A-Za-z0-9_-]{20,}"`
    must be empty.
    """
    from uk_management_bot.handlers.auth import join_with_invite

    rate_limiter_ok = AsyncMock(return_value=True)

    fake_invite_data = {
        "role": "applicant",
        "specialization": "",
        "expires_at": 9_999_999_999,
        "created_by": 1,
        "nonce": "abc123",
    }
    fake_invite_service_instance = MagicMock()
    fake_invite_service_instance.validate_invite.return_value = fake_invite_data

    fake_auth_service_instance = MagicMock()
    fake_auth_service_instance.get_user_by_telegram_id = AsyncMock(return_value=None)

    msg = _make_message(f"/join {STUB_TOKEN}", user_id=42)
    state = _make_state()
    db = _make_db()

    with caplog.at_level(logging.INFO, logger="uk_management_bot.handlers.auth"), \
        patch(
            "uk_management_bot.handlers.auth.InviteRateLimiter.is_allowed",
            new=rate_limiter_ok,
        ), \
        patch(
            "uk_management_bot.handlers.auth.InviteService",
            return_value=fake_invite_service_instance,
        ), \
        patch(
            "uk_management_bot.handlers.auth.AuthService",
            return_value=fake_auth_service_instance,
        ), \
        patch(
            "uk_management_bot.handlers.auth.get_text",
            side_effect=lambda key, language="ru", **kw: f"<text:{key}>",
        ):
        await join_with_invite(msg, state, db, language="ru")

    all_text = "\n".join(rec.getMessage() for rec in caplog.records
                         if rec.name == "uk_management_bot.handlers.auth")

    assert TOKEN_BODY not in all_text, (
        "AC failed: full invite token body leaked in handler log records. "
        f"Captured text: {all_text!r}"
    )
    assert STUB_TOKEN not in all_text, (
        "AC failed: full invite token leaked in handler log records. "
        f"Captured text: {all_text!r}"
    )
