"""
Regression tests for the P2 navigation/UX batch:

* BUG-BOT-014: ``shift_executor_assignment`` no-unassigned-shifts dead-end —
  handler must render a keyboard that contains a ``back_to_shifts`` button
  even when there are no shifts to assign.
* BUG-BOT-020: PROFILE_EDIT shows stale "не указано" after Cancel of a nested
  input FSM — the ``cancel_input`` handler must reread the user from the
  database and re-render the profile keyboard with fresh values.
* BUG-BOT-021: cancel_apartment_selection context leak — when the apartment
  picker was opened from Profile, cancel must return to the profile view
  (not the admin yards/addresses view).
* BUG-BOT-025: Employee search FSM has no message handler — typing the query
  in ``EmployeeSearchStates.waiting_for_query`` must actually run the search
  and either return inline results or an empty-state message.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import InlineKeyboardMarkup


# ─── Helpers ────────────────────────────────────────────────────────────────


def _all_callbacks(markup: InlineKeyboardMarkup) -> list:
    return [
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data
    ]


def _make_tg_user(user_id: int = 555):
    u = MagicMock()
    u.id = user_id
    u.first_name = "Test"
    u.last_name = "User"
    u.username = "testuser"
    return u


def _make_callback(data: str = "x", user_id: int = 555):
    cb = MagicMock()
    cb.data = data
    cb.from_user = _make_tg_user(user_id=user_id)
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    cb.bot = MagicMock()
    return cb


def _make_message(text: str = "", user_id: int = 555):
    msg = MagicMock()
    msg.text = text
    msg.from_user = _make_tg_user(user_id=user_id)
    msg.answer = AsyncMock()
    msg.reply = AsyncMock()
    msg.bot = MagicMock()
    return msg


def _make_state(data: dict | None = None):
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=(data or {}))
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    return state


# ─── BUG-BOT-014 ────────────────────────────────────────────────────────────


class TestBug014ShiftExecutorAssignmentBackButton:
    """No-unassigned-shifts branch must keep a working back path."""

    @pytest.mark.asyncio
    async def test_no_unassigned_branch_uses_back_capable_keyboard(self):
        # Force the early-return branch by making the SQL query yield zero rows.
        callback = _make_callback("shift_executor_assignment")
        state = _make_state()

        # DB session stub: query(...).filter(...).order_by(...).limit(...).all() = []
        db = MagicMock()
        chain = db.query.return_value.filter.return_value
        chain.order_by.return_value.limit.return_value.all.return_value = []
        db.close = MagicMock()

        with patch(
            "uk_management_bot.handlers.shift_management.analytics.get_user_language",
            return_value="ru",
        ), patch(
            "uk_management_bot.handlers.shift_management.analytics.get_text",
            side_effect=lambda key, **kw: key,
        ):
            from uk_management_bot.handlers.shift_management import (
                handle_shift_executor_assignment,
            )
            inner = getattr(handle_shift_executor_assignment, "__wrapped__", None)
            assert inner is not None, "@require_role decorator must expose __wrapped__"
            await inner(
                callback,
                state,
                db=db,
                user=MagicMock(),
                roles=["admin"],
            )

        # The keyboard rendered on the empty branch must include back_to_shifts.
        callback.message.edit_text.assert_awaited()
        kwargs = callback.message.edit_text.await_args.kwargs
        markup = kwargs.get("reply_markup")
        assert isinstance(markup, InlineKeyboardMarkup)
        assert "back_to_shifts" in _all_callbacks(markup), (
            "no-unassigned-shifts branch must keep a back-to-shifts button"
        )

    def test_executor_assignment_keyboard_has_back(self):
        """Sanity: the keyboard used on both branches exposes back_to_shifts."""
        from uk_management_bot.keyboards.shift_management import (
            get_executor_assignment_keyboard,
        )
        markup = get_executor_assignment_keyboard()
        assert "back_to_shifts" in _all_callbacks(markup)


# ─── BUG-BOT-020 ────────────────────────────────────────────────────────────


class TestBug020CancelInputRereadsUser:
    """cancel_input must reread user from DB and render keyboard with fresh values."""

    @pytest.mark.asyncio
    async def test_cancel_input_uses_fresh_db_phone_and_name(self):
        from uk_management_bot.handlers.profile_editing import handle_cancel_input

        callback = _make_callback("cancel_input")
        state = _make_state({"editing_field": "phone"})

        fresh_user = MagicMock()
        fresh_user.id = 42
        fresh_user.telegram_id = 555
        fresh_user.phone = "+79013656381"
        fresh_user.first_name = "Иван"
        fresh_user.last_name = "Иванов"
        fresh_user.username = "ivan"
        fresh_user.language = "ru"

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = fresh_user

        captured = {}

        def fake_keyboard(language="ru", user=None):
            captured["user"] = user
            captured["language"] = language
            return MagicMock(spec=InlineKeyboardMarkup)

        with patch(
            "uk_management_bot.handlers.profile_editing.get_profile_edit_keyboard",
            side_effect=fake_keyboard,
        ), patch(
            "uk_management_bot.handlers.profile_editing.get_user_language",
            return_value="ru",
        ), patch(
            "uk_management_bot.handlers.profile_editing.get_text",
            side_effect=lambda key, **kw: key,
        ):
            # AUD3-07: DI-параметр db снят — DB-фаза живёт в sync-юните под
            # run_db; тестовая сессия заходит через seam `_db`.
            await handle_cancel_input(callback, state, _db=db)

        # Handler must have queried fresh user from DB and rendered keyboard
        # with that fresh user's values (run_db-юнит отдаёт frozen DTO,
        # поэтому сверяем поля, а не identity ORM-объекта).
        rendered = captured.get("user")
        assert rendered is not None, (
            "cancel_input must re-render the keyboard with the user reread from DB"
        )
        assert rendered.phone == fresh_user.phone
        assert rendered.first_name == fresh_user.first_name
        assert rendered.last_name == fresh_user.last_name


# ─── BUG-BOT-021 ────────────────────────────────────────────────────────────


class TestBug021CancelApartmentSelectionContext:
    """A3 (аудит 2026-08-18): отмена разделена по callback_data.

    Раньше оба рукава жили в одном хендлере и различались по entry_from из
    state (BUG-BOT-021); теперь жительский рукав — cancel_apartment_selection
    в user_apartment_selection.py (вне гейта), админский — addr_cancel_selection
    в navigation.py (под RoleGate). Оба сценария остаются покрытыми.
    """

    @pytest.mark.asyncio
    async def test_cancel_from_profile_returns_to_profile_view(self):
        from uk_management_bot.handlers.user_apartment_selection import (
            cancel_apartment_selection_user,
        )

        callback = _make_callback("cancel_apartment_selection")
        state = _make_state({"entry_from": "profile"})

        with patch(
            "uk_management_bot.handlers.user_apartment_selection.get_text",
            side_effect=lambda key, **kw: key,
        ), patch(
            "uk_management_bot.handlers.user_apartments.show_my_apartments",
            new=AsyncMock(),
        ) as profile_return:
            await cancel_apartment_selection_user(callback, state, language="ru")

        profile_return.assert_awaited()

    @pytest.mark.asyncio
    async def test_admin_cancel_returns_to_admin_view(self):
        from uk_management_bot.handlers.address_apartments import (
            cancel_apartment_action,
        )

        callback = _make_callback("addr_cancel_selection")
        state = _make_state({})

        with patch(
            "uk_management_bot.handlers.address_apartments.navigation.get_text",
            side_effect=lambda key, **kw: key,
        ), patch(
            "uk_management_bot.handlers.address_apartments.navigation._return_to_admin_yards",
            new=AsyncMock(return_value=True),
        ) as admin_return:
            await cancel_apartment_action(callback, state, language="ru")

        admin_return.assert_awaited()

    @pytest.mark.asyncio
    async def test_resident_cancel_from_onboarding_goes_to_documents(self):
        """Из онбординга отмена ведёт на шаг документов (как confirm-путь),
        сохраняя регистрационные данные state."""
        from uk_management_bot.handlers.user_apartment_selection import (
            cancel_apartment_selection_user,
        )
        from uk_management_bot.states.onboarding import OnboardingStates

        callback = _make_callback("cancel_apartment_selection")
        state = _make_state({"phone": "+7999", "selected_yard_id": 3})
        state.get_state = AsyncMock(
            return_value=OnboardingStates.waiting_for_yard_selection.state
        )
        state.set_state = AsyncMock()
        state.update_data = AsyncMock()

        with patch(
            "uk_management_bot.handlers.user_apartment_selection.get_text",
            side_effect=lambda key, **kw: key,
        ), patch(
            "uk_management_bot.keyboards.onboarding.get_document_type_keyboard",
            return_value=None,
        ):
            await cancel_apartment_selection_user(callback, state, language="ru")

        state.set_state.assert_awaited_once_with(OnboardingStates.waiting_for_document_type)
        state.clear.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_resident_cancel_stateless_only_cancels(self):
        """Просроченная кнопка вне состояния: только «отменено», никаких меню."""
        from uk_management_bot.handlers.user_apartment_selection import (
            cancel_apartment_selection_user,
        )

        callback = _make_callback("cancel_apartment_selection")
        state = _make_state({})
        state.get_state = AsyncMock(return_value=None)

        with patch(
            "uk_management_bot.handlers.user_apartment_selection.get_text",
            side_effect=lambda key, **kw: key,
        ), patch(
            "uk_management_bot.handlers.user_apartments.show_my_apartments",
            new=AsyncMock(),
        ) as profile_return:
            await cancel_apartment_selection_user(callback, state, language="ru")

        profile_return.assert_not_awaited()
        state.clear.assert_awaited()
        callback.message.answer.assert_not_called()


# ─── BUG-BOT-025 ────────────────────────────────────────────────────────────


class TestBug025EmployeeSearchHandler:
    """waiting_for_search_query FSM message must run a DB ILIKE search."""

    @pytest.mark.asyncio
    async def test_search_handler_returns_results(self):
        from uk_management_bot.handlers.employee_management import (
            handle_employee_search_query,
        )

        msg = _make_message(text="иван")
        state = _make_state()

        emp = MagicMock()
        emp.id = 7
        emp.telegram_id = 100
        emp.first_name = "Иван"
        emp.last_name = "Иванов"
        emp.phone = "+79991112233"
        emp.username = "ivan"

        db = MagicMock()
        # query(User).filter(or_(...)).limit(N).all() → [emp]
        db.query.return_value.filter.return_value.limit.return_value.all.return_value = [emp]

        with patch(
            "uk_management_bot.handlers.employee_management.lists.get_text",
            side_effect=lambda key, **kw: key,
        ), patch(
            "uk_management_bot.handlers.employee_management.lists.has_admin_access",
            return_value=True,
        ):
            await handle_employee_search_query(
                msg, state, _db=db, user=MagicMock(), roles=["admin"], language="ru"
            )

        msg.answer.assert_awaited()
        call = msg.answer.await_args
        # On non-empty results, a keyboard with at least one inline button must be present.
        markup = call.kwargs.get("reply_markup")
        assert isinstance(markup, InlineKeyboardMarkup)
        # 1 row for the employee + 1 row for the cancel button → at least 1 non-empty row.
        assert len(markup.inline_keyboard) >= 1
        assert any(
            btn.callback_data == "employee_view_7"
            for row in markup.inline_keyboard
            for btn in row
        ), "result rows must reference the matched employee"

    @pytest.mark.asyncio
    async def test_search_handler_returns_empty_state(self):
        from uk_management_bot.handlers.employee_management import (
            handle_employee_search_query,
        )

        msg = _make_message(text="нетуnetu")
        state = _make_state()

        db = MagicMock()
        db.query.return_value.filter.return_value.limit.return_value.all.return_value = []

        with patch(
            "uk_management_bot.handlers.employee_management.lists.get_text",
            side_effect=lambda key, **kw: key,
        ), patch(
            "uk_management_bot.handlers.employee_management.lists.has_admin_access",
            return_value=True,
        ):
            await handle_employee_search_query(
                msg, state, _db=db, user=MagicMock(), roles=["admin"], language="ru"
            )

        msg.answer.assert_awaited()
        args = msg.answer.await_args.args
        kwargs = msg.answer.await_args.kwargs
        text_arg = args[0] if args else kwargs.get("text", "")
        assert "not_found" in text_arg or "empty" in text_arg.lower(), (
            f"empty-state message should reference 'not_found' / 'empty' key, got: {text_arg}"
        )
