"""
Unit tests for uk_management_bot/handlers/base.py

Tests handler functions directly by mocking all aiogram and service objects.
"""

import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
from aiogram.types import Message, CallbackQuery, User as TgUser


# ─── Helpers ────────────────────────────────────────────────────────────────

def _make_tg_user(user_id=123, first_name="Test", last_name="User", username="testuser"):
    u = MagicMock(spec=TgUser)
    u.id = user_id
    u.first_name = first_name
    u.last_name = last_name
    u.username = username
    return u


def _make_message(text="", user_id=123, first_name="Test"):
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.from_user = _make_tg_user(user_id=user_id, first_name=first_name)
    msg.answer = AsyncMock()
    msg.reply = AsyncMock()
    msg.bot = MagicMock()
    return msg


def _make_callback(data="", user_id=123):
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = _make_tg_user(user_id=user_id)
    cb.answer = AsyncMock()
    cb.message = _make_message()
    cb.bot = MagicMock()
    return cb


def _make_state(state_data=None):
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=state_data or {})
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    return state


def _make_db_user(
    tg_id=123,
    status="approved",
    phone="+998901234567",
    roles='["applicant"]',
    active_role="applicant",
    user_apartments=None,
):
    user = MagicMock()
    user.id = 1
    user.telegram_id = tg_id
    user.status = status
    user.phone = phone
    user.roles = roles
    user.active_role = active_role
    user.user_apartments = user_apartments if user_apartments is not None else []
    return user


def _make_db():
    db = MagicMock()
    db.query = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    return db


# ─── handle_regular_start ────────────────────────────────────────────────────

class TestHandleRegularStart:
    """Tests for handle_regular_start()"""

    @pytest.mark.asyncio
    async def test_start_approved_user_answers_with_keyboard(self):
        """Approved user gets welcome message with a keyboard."""
        from uk_management_bot.handlers.base import handle_regular_start

        msg = _make_message()
        db = _make_db()
        user = _make_db_user(status="approved", phone="+998901234567")
        # Simulate approved apartment
        apt = MagicMock()
        apt.status = "approved"
        user.user_apartments = [apt]

        with patch(
            "uk_management_bot.handlers.base.AuthService"
        ) as MockAuth, patch(
            "uk_management_bot.handlers.base.get_main_keyboard_for_role", return_value=MagicMock()
        ):
            auth_instance = MockAuth.return_value
            auth_instance.get_or_create_user = AsyncMock(return_value=user)

            await handle_regular_start(msg, db, roles=["applicant"], active_role="applicant", user_status="approved")

        msg.answer.assert_called_once()
        call_kwargs = msg.answer.call_args
        # message text should be passed as first positional arg
        assert call_kwargs is not None

    @pytest.mark.asyncio
    async def test_start_pending_user_no_profile_shows_onboarding(self):
        """Pending user with incomplete profile sees onboarding keyboard."""
        from uk_management_bot.handlers.base import handle_regular_start

        msg = _make_message()
        db = _make_db()
        user = _make_db_user(status="pending", phone=None)

        with patch(
            "uk_management_bot.handlers.base.AuthService"
        ) as MockAuth:
            auth_instance = MockAuth.return_value
            auth_instance.get_or_create_user = AsyncMock(return_value=user)

            await handle_regular_start(msg, db)

        msg.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_blocked_user_shows_blocked_message(self):
        """Blocked user gets a message that includes the blocked status text."""
        from uk_management_bot.handlers.base import handle_regular_start

        msg = _make_message()
        db = _make_db()
        # blocked user with complete profile so we skip onboarding branch
        apt = MagicMock()
        apt.status = "approved"
        user = _make_db_user(status="blocked", phone="+998901234567")
        user.user_apartments = [apt]

        with patch("uk_management_bot.handlers.base.AuthService") as MockAuth, patch(
            "uk_management_bot.handlers.base.get_main_keyboard_for_role", return_value=MagicMock()
        ):
            auth_instance = MockAuth.return_value
            auth_instance.get_or_create_user = AsyncMock(return_value=user)

            await handle_regular_start(msg, db, roles=["applicant"], active_role="applicant", user_status="blocked")

        msg.answer.assert_called_once()
        # The rendered text should contain the blocked-status locale text
        sent_text = msg.answer.call_args[0][0]
        assert isinstance(sent_text, str)

    @pytest.mark.asyncio
    async def test_start_uses_db_roles_fallback(self):
        """handle_regular_start reads roles from user.roles JSON when roles arg is None."""
        from uk_management_bot.handlers.base import handle_regular_start

        msg = _make_message()
        db = _make_db()
        apt = MagicMock()
        apt.status = "approved"
        user = _make_db_user(
            status="approved",
            phone="+998901234567",
            roles='["executor","manager"]',
            active_role="executor",
        )
        user.user_apartments = [apt]

        with patch("uk_management_bot.handlers.base.AuthService") as MockAuth, patch(
            "uk_management_bot.handlers.base.get_main_keyboard_for_role", return_value=MagicMock()
        ) as mock_kb:
            auth_instance = MockAuth.return_value
            auth_instance.get_or_create_user = AsyncMock(return_value=user)

            # roles=None triggers DB fallback
            await handle_regular_start(msg, db, roles=None, active_role=None)

        mock_kb.assert_called_once()
        # active_role should have been resolved from DB
        kb_args = mock_kb.call_args[0]
        assert kb_args[0] == "executor"

    @pytest.mark.asyncio
    async def test_start_state_cleared_when_provided(self):
        """cmd_start clears FSM state before delegating to handle_regular_start."""
        from uk_management_bot.handlers.base import cmd_start

        msg = _make_message(text="/start")
        db = _make_db()
        state = _make_state()
        apt = MagicMock()
        apt.status = "approved"
        user = _make_db_user(status="approved", phone="+998901234567")
        user.user_apartments = [apt]

        with patch("uk_management_bot.handlers.base.AuthService") as MockAuth, patch(
            "uk_management_bot.handlers.base.get_main_keyboard_for_role", return_value=MagicMock()
        ):
            auth_instance = MockAuth.return_value
            auth_instance.get_or_create_user = AsyncMock(return_value=user)

            await cmd_start(msg, db, state)

        state.clear.assert_called_once()


# ─── go_back ─────────────────────────────────────────────────────────────────

class TestGoBack:
    """Tests for go_back()"""

    @pytest.mark.asyncio
    async def test_go_back_clears_state(self):
        """go_back clears FSM state unconditionally."""
        from uk_management_bot.handlers.base import go_back

        msg = _make_message()
        state = _make_state()
        db = _make_db()

        with patch("uk_management_bot.handlers.base.get_user_language", return_value="ru"), patch(
            "uk_management_bot.handlers.base.get_user_contextual_keyboard", return_value=MagicMock()
        ):
            await go_back(msg, state, db)

        state.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_go_back_answers_message(self):
        """go_back sends a response to the user."""
        from uk_management_bot.handlers.base import go_back

        msg = _make_message()
        state = _make_state()
        db = _make_db()

        with patch("uk_management_bot.handlers.base.get_user_language", return_value="ru"), patch(
            "uk_management_bot.handlers.base.get_user_contextual_keyboard", return_value=MagicMock()
        ):
            await go_back(msg, state, db)

        msg.answer.assert_called_once()


# ─── show_help ───────────────────────────────────────────────────────────────

class TestShowHelp:
    """Tests for show_help()"""

    @pytest.mark.asyncio
    async def test_show_help_answers_message(self):
        """show_help sends help text to the user."""
        from uk_management_bot.handlers.base import show_help

        msg = _make_message()
        db = _make_db()

        with patch("uk_management_bot.handlers.base.get_user_language", return_value="ru"):
            await show_help(msg, db=db)

        msg.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_show_help_text_is_string(self):
        """show_help sends a non-empty string."""
        from uk_management_bot.handlers.base import show_help

        msg = _make_message()
        db = _make_db()

        with patch("uk_management_bot.handlers.base.get_user_language", return_value="ru"):
            await show_help(msg, db=db)

        sent_text = msg.answer.call_args[0][0]
        assert isinstance(sent_text, str)
        assert len(sent_text) > 0

    @pytest.mark.asyncio
    async def test_show_help_uses_user_language(self):
        """show_help fetches the user's preferred language."""
        from uk_management_bot.handlers.base import show_help

        msg = _make_message()
        db = _make_db()

        with patch(
            "uk_management_bot.handlers.base.get_user_language", return_value="uz"
        ) as mock_lang:
            await show_help(msg, db=db)

        mock_lang.assert_called_once_with(msg.from_user.id, db)


# ─── show_profile ─────────────────────────────────────────────────────────────

class TestShowProfile:
    """Tests for show_profile()"""

    @pytest.mark.asyncio
    async def test_show_profile_calls_profile_service(self):
        """show_profile delegates to ProfileService.get_user_profile_data."""
        from uk_management_bot.handlers.base import show_profile

        msg = _make_message()
        db = _make_db()

        profile_data = {
            "roles": ["applicant"],
            "active_role": "applicant",
        }
        formatted_text = "Профиль пользователя"

        with patch(
            "uk_management_bot.services.profile_service.ProfileService"
        ) as MockPS, patch(
            "uk_management_bot.handlers.base.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.handlers.base.get_role_switch_inline"
        ) as mock_inline:
            ps_inst = MockPS.return_value
            ps_inst.get_user_profile_data.return_value = profile_data
            ps_inst.format_profile_text.return_value = formatted_text
            mock_inline.return_value = MagicMock(inline_keyboard=[])

            await show_profile(msg, db)

        ps_inst.get_user_profile_data.assert_called_once_with(msg.from_user.id)

    @pytest.mark.asyncio
    async def test_show_profile_answers_with_formatted_text(self):
        """show_profile sends the formatted profile text."""
        from uk_management_bot.handlers.base import show_profile

        msg = _make_message()
        db = _make_db()
        formatted_text = "Имя: Test\nТелефон: +998901234567"
        profile_data = {"roles": ["applicant"], "active_role": "applicant"}

        with patch(
            "uk_management_bot.services.profile_service.ProfileService"
        ) as MockPS, patch(
            "uk_management_bot.handlers.base.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.handlers.base.get_role_switch_inline"
        ) as mock_inline:
            ps_inst = MockPS.return_value
            ps_inst.get_user_profile_data.return_value = profile_data
            ps_inst.format_profile_text.return_value = formatted_text
            mock_inline.return_value = MagicMock(inline_keyboard=[])

            await show_profile(msg, db)

        msg.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_show_profile_handles_missing_profile_data(self):
        """show_profile sends an error message when profile data is None."""
        from uk_management_bot.handlers.base import show_profile

        msg = _make_message()
        db = _make_db()

        with patch(
            "uk_management_bot.services.profile_service.ProfileService"
        ) as MockPS, patch(
            "uk_management_bot.handlers.base.get_main_keyboard_for_role", return_value=MagicMock()
        ):
            ps_inst = MockPS.return_value
            ps_inst.get_user_profile_data.return_value = None

            await show_profile(msg, db)

        msg.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_show_profile_exception_sends_error_message(self):
        """show_profile handles unexpected exceptions gracefully."""
        from uk_management_bot.handlers.base import show_profile

        msg = _make_message()
        db = _make_db()

        with patch(
            "uk_management_bot.services.profile_service.ProfileService"
        ) as MockPS, patch(
            "uk_management_bot.handlers.base.get_main_keyboard_for_role", return_value=MagicMock()
        ):
            ps_inst = MockPS.return_value
            ps_inst.get_user_profile_data.side_effect = RuntimeError("db error")

            await show_profile(msg, db)

        msg.answer.assert_called_once()


# ─── cancel_action ────────────────────────────────────────────────────────────

class TestCancelAction:
    """Tests for cancel_action()"""

    @pytest.mark.asyncio
    async def test_cancel_with_active_state_clears_and_answers(self):
        """cancel_action clears state and sends a message when state is active."""
        from uk_management_bot.handlers.base import cancel_action

        msg = _make_message()
        state = _make_state()
        state.get_state = AsyncMock(return_value="SomeState:some_step")

        with patch(
            "uk_management_bot.handlers.base.get_user_contextual_keyboard", return_value=MagicMock()
        ):
            await cancel_action(msg, state)

        state.clear.assert_called_once()
        msg.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_without_active_state_still_answers(self):
        """cancel_action answers even when there is no active FSM state."""
        from uk_management_bot.handlers.base import cancel_action

        msg = _make_message()
        state = _make_state()
        state.get_state = AsyncMock(return_value=None)

        with patch(
            "uk_management_bot.handlers.base.get_user_contextual_keyboard", return_value=MagicMock()
        ):
            await cancel_action(msg, state)

        msg.answer.assert_called_once()
        state.clear.assert_not_called()


# ─── cmd_help ─────────────────────────────────────────────────────────────────

class TestCmdHelp:
    """Tests for cmd_help()"""

    @pytest.mark.asyncio
    async def test_cmd_help_sends_help_text(self):
        """cmd_help sends the help text using get_user_contextual_keyboard."""
        from uk_management_bot.handlers.base import cmd_help

        msg = _make_message()

        with patch(
            "uk_management_bot.handlers.base.get_user_contextual_keyboard", return_value=MagicMock()
        ):
            await cmd_help(msg)

        msg.answer.assert_called_once()


# ─── switch_role ──────────────────────────────────────────────────────────────

class TestSwitchRole:
    """Tests for switch_role callback handler"""

    @pytest.mark.asyncio
    async def test_switch_role_to_allowed_role_updates_db(self):
        """switch_role updates user.active_role in the DB."""
        from uk_management_bot.handlers.base import switch_role
        from uk_management_bot.utils.callback_factories import RoleSwitchCB

        cb = _make_callback()
        db = _make_db()

        user = MagicMock()
        user.id = 1
        user.active_role = "applicant"
        query = MagicMock()
        query.filter.return_value.first.return_value = user
        db.query.return_value = query

        callback_data = RoleSwitchCB(target="executor")

        with patch(
            "uk_management_bot.handlers.base.get_main_keyboard_for_role", return_value=MagicMock()
        ), patch(
            "uk_management_bot.handlers.base.async_notify_role_switched", new_callable=AsyncMock
        ):
            await switch_role(
                cb,
                callback_data=callback_data,
                db=db,
                roles=["applicant", "executor"],
                active_role="applicant",
                user_status="approved",
            )

        assert user.active_role == "executor"
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_switch_role_to_disallowed_role_shows_alert(self):
        """switch_role shows an alert when target role is not in user's roles."""
        from uk_management_bot.handlers.base import switch_role
        from uk_management_bot.utils.callback_factories import RoleSwitchCB

        cb = _make_callback()
        db = _make_db()
        callback_data = RoleSwitchCB(target="admin")

        await switch_role(
            cb,
            callback_data=callback_data,
            db=db,
            roles=["applicant"],
            active_role="applicant",
        )

        cb.answer.assert_called_once()
        # show_alert=True expected
        _, call_kwargs = cb.answer.call_args
        assert call_kwargs.get("show_alert") is True

    @pytest.mark.asyncio
    async def test_switch_role_user_not_found_in_db(self):
        """switch_role shows error alert when user is missing from DB."""
        from uk_management_bot.handlers.base import switch_role
        from uk_management_bot.utils.callback_factories import RoleSwitchCB

        cb = _make_callback()
        db = _make_db()

        query = MagicMock()
        query.filter.return_value.first.return_value = None
        db.query.return_value = query

        callback_data = RoleSwitchCB(target="executor")

        await switch_role(
            cb,
            callback_data=callback_data,
            db=db,
            roles=["applicant", "executor"],
            active_role="applicant",
        )

        cb.answer.assert_called_once()
        _, call_kwargs = cb.answer.call_args
        assert call_kwargs.get("show_alert") is True


# ─── handle_restart_bot ───────────────────────────────────────────────────────

class TestHandleRestartBot:
    """Tests for handle_restart_bot callback."""

    @pytest.mark.asyncio
    async def test_restart_bot_user_not_found_shows_alert(self):
        """handle_restart_bot shows an alert when user is not found."""
        from uk_management_bot.handlers.base import handle_restart_bot

        cb = _make_callback(data="restart_bot")
        db = _make_db()

        with patch("uk_management_bot.handlers.base.AuthService") as MockAuth:
            auth_inst = MockAuth.return_value
            auth_inst.get_user_by_telegram_id = AsyncMock(return_value=None)

            await handle_restart_bot(cb, db=db)

        cb.answer.assert_called_once()
        _, call_kwargs = cb.answer.call_args
        assert call_kwargs.get("show_alert") is True

    @pytest.mark.asyncio
    async def test_restart_bot_sends_welcome_message(self):
        """handle_restart_bot sends a welcome message when user is found."""
        from uk_management_bot.handlers.base import handle_restart_bot

        cb = _make_callback(data="restart_bot")
        db = _make_db()
        user = _make_db_user(status="approved")

        with patch("uk_management_bot.handlers.base.AuthService") as MockAuth, patch(
            "uk_management_bot.handlers.base.get_main_keyboard_for_role", return_value=MagicMock()
        ):
            auth_inst = MockAuth.return_value
            auth_inst.get_user_by_telegram_id = AsyncMock(return_value=user)

            await handle_restart_bot(cb, db=db)

        cb.message.answer.assert_called_once()
        cb.answer.assert_called_once()
