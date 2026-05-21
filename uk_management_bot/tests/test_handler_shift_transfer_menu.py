"""
Smoke tests for the ``shift_transfer_menu`` callback in handlers/my_shifts.py
(BUG-BOT-006).

The original bug was caused by ``with get_db() as db:`` — ``get_db`` is a plain
generator, so the context-manager protocol raised ``TypeError`` and the handler
fell through to the ``except`` branch with "Ошибка загрузки меню".

These tests prove:
  1. The handler runs to completion without raising / falling into the error
     branch when the DB returns a valid user.
  2. The user-facing "loading menu" error answer is NOT triggered on the happy
     path.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message, User as TgUser


def _make_callback(user_id=42):
    tg_user = MagicMock(spec=TgUser)
    tg_user.id = user_id

    message = MagicMock(spec=Message)
    message.edit_text = AsyncMock()

    cb = MagicMock(spec=CallbackQuery)
    cb.from_user = tg_user
    cb.message = message
    cb.answer = AsyncMock()
    return cb


def _make_db(user, active_shifts=None, transfers=None):
    """Build a mock session that returns the supplied user / shifts / transfers."""
    active_shifts = active_shifts or []
    transfers = transfers or []

    def query_side_effect(model):
        from uk_management_bot.database.models.shift import Shift
        from uk_management_bot.database.models.shift_transfer import ShiftTransfer
        from uk_management_bot.database.models.user import User

        q = MagicMock()
        q.filter.return_value = q
        q.options.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q

        if model is User:
            q.first.return_value = user
        elif model is Shift:
            q.all.return_value = active_shifts
        elif model is ShiftTransfer:
            q.all.return_value = transfers
        else:
            q.all.return_value = []
            q.first.return_value = None
        return q

    db = MagicMock()
    db.query.side_effect = query_side_effect
    db.close = MagicMock()
    return db


@pytest.mark.asyncio
class TestShiftTransferMenuHandler:
    async def test_menu_renders_without_falling_into_error_branch(self):
        """Happy path: handler edits message instead of answering with error."""
        from uk_management_bot.handlers.my_shifts import handle_shift_transfer_menu

        cb = _make_callback(user_id=42)

        user = MagicMock()
        user.telegram_id = 42

        db = _make_db(user=user)

        # next(get_db()) returns our mock session.
        with patch(
            "uk_management_bot.handlers.my_shifts.get_db",
            return_value=iter([db]),
        ), patch(
            "uk_management_bot.handlers.my_shifts.get_text",
            side_effect=lambda key, language="ru", **kw: key,
        ):
            await handle_shift_transfer_menu(cb, state=MagicMock(), language="ru")

        # Menu was rendered (edit_text called) and no error popup was raised.
        cb.message.edit_text.assert_called_once()
        for call in cb.answer.call_args_list:
            args, kwargs = call
            text = args[0] if args else kwargs.get("text", "")
            assert "error_loading_menu" not in text
        db.close.assert_called_once()

    async def test_unknown_user_returns_user_not_found(self):
        """If user lookup fails, the handler returns user_not_found, not error_loading_menu."""
        from uk_management_bot.handlers.my_shifts import handle_shift_transfer_menu

        cb = _make_callback(user_id=99)
        db = _make_db(user=None)

        with patch(
            "uk_management_bot.handlers.my_shifts.get_db",
            return_value=iter([db]),
        ), patch(
            "uk_management_bot.handlers.my_shifts.get_text",
            side_effect=lambda key, language="ru", **kw: key,
        ):
            await handle_shift_transfer_menu(cb, state=MagicMock(), language="ru")

        cb.answer.assert_called_once()
        text = cb.answer.call_args[0][0]
        assert "user_not_found" in text
        # session must still be closed even on early-return
        db.close.assert_called_once()
