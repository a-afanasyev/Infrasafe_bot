"""
Tests for the WebApp registration button on the new-user welcome keyboard.

Task 9: a pending user with an incomplete profile should see an ADDITIONAL
reply-keyboard button whose web_app.url points at the React register Mini App
(f"{settings.FRONTEND_URL}/uk/register"). When FRONTEND_URL is empty the button
must be omitted (no crash).
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from aiogram.types import Message, User as TgUser


# ─── Helpers (mirrors test_handler_base.py style) ────────────────────────────

def _make_tg_user(user_id=123, first_name="Test", last_name="User", username="testuser"):
    u = MagicMock(spec=TgUser)
    u.id = user_id
    u.first_name = first_name
    u.last_name = last_name
    u.username = username
    return u


def _make_message(text="", user_id=123):
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.from_user = _make_tg_user(user_id=user_id)
    msg.answer = AsyncMock()
    msg.reply = AsyncMock()
    msg.bot = MagicMock()
    return msg


def _make_db():
    db = MagicMock()
    db.query = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    return db


def _make_pending_user(tg_id=123):
    """New pending user with incomplete profile (no phone, no apartment)."""
    user = MagicMock()
    user.id = 1
    user.telegram_id = tg_id
    user.status = "pending"
    user.phone = None
    user.roles = '["applicant"]'
    user.active_role = "applicant"
    user.user_apartments = []
    return user


def _iter_buttons(reply_markup):
    """Flatten a ReplyKeyboardMarkup into a list of KeyboardButton objects."""
    buttons = []
    for row in reply_markup.keyboard:
        for btn in row:
            buttons.append(btn)
    return buttons


# ─── Tests ───────────────────────────────────────────────────────────────────

class TestRegisterWebAppButton:
    """WebApp registration button on the onboarding keyboard."""

    @pytest.mark.asyncio
    async def test_webapp_button_present_when_frontend_url_set(self, monkeypatch):
        """When FRONTEND_URL is set, onboarding keyboard contains a WebApp
        button whose web_app.url ends with /register."""
        from uk_management_bot.handlers import base
        from uk_management_bot.handlers.base import handle_regular_start

        monkeypatch.setattr(base.settings, "FRONTEND_URL", "https://example.test")

        msg = _make_message()
        db = _make_db()
        user = _make_pending_user()

        with patch("uk_management_bot.handlers.base.AuthService") as MockAuth:
            MockAuth.return_value.get_or_create_user = AsyncMock(return_value=user)
            await handle_regular_start(msg, db)

        msg.answer.assert_called_once()
        reply_markup = msg.answer.call_args.kwargs.get("reply_markup")
        assert reply_markup is not None

        webapp_urls = [
            btn.web_app.url
            for btn in _iter_buttons(reply_markup)
            if getattr(btn, "web_app", None) is not None
        ]
        assert any(url.endswith("/register") for url in webapp_urls), (
            f"expected a web_app button ending in /register, got {webapp_urls}"
        )

    @pytest.mark.asyncio
    async def test_webapp_button_absent_when_frontend_url_empty(self, monkeypatch):
        """When FRONTEND_URL is empty, no WebApp button is emitted and no crash."""
        from uk_management_bot.handlers import base
        from uk_management_bot.handlers.base import handle_regular_start

        monkeypatch.setattr(base.settings, "FRONTEND_URL", "")

        msg = _make_message()
        db = _make_db()
        user = _make_pending_user()

        with patch("uk_management_bot.handlers.base.AuthService") as MockAuth:
            MockAuth.return_value.get_or_create_user = AsyncMock(return_value=user)
            await handle_regular_start(msg, db)

        msg.answer.assert_called_once()
        reply_markup = msg.answer.call_args.kwargs.get("reply_markup")
        assert reply_markup is not None

        webapp_buttons = [
            btn
            for btn in _iter_buttons(reply_markup)
            if getattr(btn, "web_app", None) is not None
        ]
        assert webapp_buttons == [], (
            f"expected no web_app buttons when FRONTEND_URL empty, got {webapp_buttons}"
        )
