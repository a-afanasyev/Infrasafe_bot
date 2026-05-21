"""
Tests for uk_management_bot/web/api/invite.py::register_via_invite

Focuses on the new-user branch which previously raised NameError because it
referenced an undefined ``user_data`` variable instead of splitting
``data.full_name`` like the existing-user branch does (FIX-001).

Strategy: invoke ``register_via_invite`` directly as an async function with
mocked ``InviteService``/``AuthService`` and a mocked DB session, bypassing
FastAPI app/router wiring (avoids legacy-import side effects from full app
bootstrap — see TEST-069).
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request


def _make_request() -> Request:
    """Build a minimal valid starlette Request (slowapi requires a real one)."""
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
    """Run an async coroutine to completion in a fresh event loop."""
    return asyncio.run(coro)


def _make_db_no_existing_user() -> MagicMock:
    """Mock DB session whose ``query(...).filter(...).first()`` returns None."""
    db = MagicMock()
    query = MagicMock()
    db.query.return_value = query
    query.filter.return_value = query
    query.first.return_value = None
    return db


def _make_registration_data(
    *,
    token: str = "valid-token",
    full_name: str = "Иван Петров",
    specialization: str = "plumber",
    telegram_id: int = 555_123_456,
):
    from uk_management_bot.web.api.invite import RegistrationData

    return RegistrationData(
        token=token,
        full_name=full_name,
        specialization=specialization,
        telegram_id=telegram_id,
    )


class TestRegisterViaInviteNewUser:
    """New-user branch (telegram_id not in DB) — formerly hit NameError."""

    def test_new_user_registration_succeeds(self):
        """
        POST /api/register with NEW telegram_id and a valid token should
        return success and pass split first/last names from full_name into
        InviteService.join_via_invite (mirroring existing-user branch).
        """
        from uk_management_bot.web.api import invite as invite_module

        db = _make_db_no_existing_user()
        data = _make_registration_data(full_name="Иван Петров")

        mock_invite_instance = MagicMock()
        mock_invite_instance.join_via_invite.return_value = {
            "success": True,
            "user_id": 42,
        }
        mock_auth_instance = MagicMock()

        request = _make_request()

        with patch.object(
            invite_module, "InviteService", return_value=mock_invite_instance
        ), patch.object(
            invite_module, "AuthService", return_value=mock_auth_instance
        ):
            result = _run(
                invite_module.register_via_invite(
                    request=request, data=data, db=db
                )
            )

        assert result == {
            "success": True,
            "message": "Регистрация успешно завершена",
            "user_id": 42,
        }
        mock_invite_instance.join_via_invite.assert_called_once_with(
            token="valid-token",
            telegram_id=555_123_456,
            first_name="Иван",
            last_name="Петров",
            specialization="plumber",
        )

    def test_new_user_single_name_has_empty_last_name(self):
        """Single-word full_name → first_name set, last_name empty string."""
        from uk_management_bot.web.api import invite as invite_module

        db = _make_db_no_existing_user()
        data = _make_registration_data(full_name="Иван")

        mock_invite_instance = MagicMock()
        mock_invite_instance.join_via_invite.return_value = {
            "success": True,
            "user_id": 7,
        }
        request = _make_request()

        with patch.object(
            invite_module, "InviteService", return_value=mock_invite_instance
        ), patch.object(invite_module, "AuthService", return_value=MagicMock()):
            _run(
                invite_module.register_via_invite(
                    request=request, data=data, db=db
                )
            )

        call_kwargs = mock_invite_instance.join_via_invite.call_args.kwargs
        assert call_kwargs["first_name"] == "Иван"
        assert call_kwargs["last_name"] == ""

    def test_new_user_multi_word_last_name(self):
        """Multi-word names: 1st token → first_name, rest joined → last_name."""
        from uk_management_bot.web.api import invite as invite_module

        db = _make_db_no_existing_user()
        data = _make_registration_data(full_name="Иван Петрович Петров")

        mock_invite_instance = MagicMock()
        mock_invite_instance.join_via_invite.return_value = {
            "success": True,
            "user_id": 9,
        }
        request = _make_request()

        with patch.object(
            invite_module, "InviteService", return_value=mock_invite_instance
        ), patch.object(invite_module, "AuthService", return_value=MagicMock()):
            _run(
                invite_module.register_via_invite(
                    request=request, data=data, db=db
                )
            )

        call_kwargs = mock_invite_instance.join_via_invite.call_args.kwargs
        assert call_kwargs["first_name"] == "Иван"
        assert call_kwargs["last_name"] == "Петрович Петров"
