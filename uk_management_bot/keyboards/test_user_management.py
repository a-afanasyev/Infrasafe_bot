"""
Unit tests for keyboards/user_management.py

Mocks get_text and any DB/service calls that occur inside keyboard functions.
Tests focus on return types, button counts, and callback-data conventions.
"""
import pytest
from unittest.mock import patch, MagicMock

from aiogram.types import InlineKeyboardMarkup

GET_TEXT_PATH = "uk_management_bot.keyboards.user_management.get_text"


def _echo(key: str, language: str = "ru", **kwargs) -> str:
    return key


def _flat_texts(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.text for row in markup.inline_keyboard for btn in row]


def _flat_cbs(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row]


def _make_user(uid: int = 1, status: str = "pending",
               roles: list | None = None) -> MagicMock:
    user = MagicMock()
    user.id = uid
    user.telegram_id = 100 + uid
    user.status = status
    user.roles = roles or ["applicant"]
    user.first_name = "Test"
    user.last_name = "User"
    user.username = "testuser"
    return user


# ---------------------------------------------------------------------------
# get_user_management_main_keyboard
# ---------------------------------------------------------------------------

class TestGetUserManagementMainKeyboard:
    def test_returns_inline_keyboard_markup(self):
        stats = {"pending": 3, "approved": 10, "blocked": 1, "staff": 5}
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_user_management_main_keyboard
            result = get_user_management_main_keyboard(stats)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_seven_buttons(self):
        stats = {"pending": 0, "approved": 0, "blocked": 0, "staff": 0}
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_user_management_main_keyboard
            result = get_user_management_main_keyboard(stats)
        # stats + pending + approved + blocked + staff + search + back = 7
        assert len(_flat_texts(result)) == 7

    def test_stats_counts_embedded_in_button_text(self):
        stats = {"pending": 5, "approved": 0, "blocked": 0, "staff": 0}
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_user_management_main_keyboard
            result = get_user_management_main_keyboard(stats)
        texts = _flat_texts(result)
        assert any("5" in t for t in texts)

    def test_admin_panel_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_user_management_main_keyboard
            result = get_user_management_main_keyboard({})
        assert "admin_panel" in _flat_cbs(result)


# ---------------------------------------------------------------------------
# get_user_list_keyboard
# ---------------------------------------------------------------------------

class TestGetUserListKeyboard:
    def _make_users_data(self, users=None, page=1, total_pages=1,
                         has_prev=False, has_next=False):
        return {
            "users": users or [],
            "page": page,
            "total_pages": total_pages,
            "has_prev": has_prev,
            "has_next": has_next,
        }

    def test_returns_inline_keyboard_markup(self):
        data = self._make_users_data()
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_user_list_keyboard
            result = get_user_list_keyboard(data, "pending")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_empty_users_shows_no_users_found_button(self):
        data = self._make_users_data()
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_user_list_keyboard
            result = get_user_list_keyboard(data, "pending")
        cbs = _flat_cbs(result)
        assert "user_mgmt_nop" in cbs

    def test_user_button_callback_contains_user_id(self):
        user = _make_user(uid=7, status="pending")
        data = self._make_users_data(users=[user])
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_user_list_keyboard
            result = get_user_list_keyboard(data, "pending")
        cbs = _flat_cbs(result)
        assert any("user_mgmt_user_7" in cb for cb in cbs)

    def test_pagination_shows_next_button_when_has_next(self):
        data = self._make_users_data(has_next=True, page=1, total_pages=3)
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_user_list_keyboard
            result = get_user_list_keyboard(data, "pending")
        cbs = _flat_cbs(result)
        assert any("pending_2" in cb for cb in cbs)

    def test_back_to_main_callback(self):
        data = self._make_users_data()
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_user_list_keyboard
            result = get_user_list_keyboard(data, "approved")
        assert "user_mgmt_main" in _flat_cbs(result)


# ---------------------------------------------------------------------------
# get_user_actions_keyboard
# ---------------------------------------------------------------------------

class TestGetUserActionsKeyboard:
    def _call(self, user, language="ru"):
        # The function has a try/except around DB access, so it is resilient
        # to DB being unavailable in tests — the fallback path always adds
        # the documents button.  We only need to mock get_text.
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_user_actions_keyboard
            return get_user_actions_keyboard(user, language)

    def test_returns_inline_keyboard_markup(self):
        user = _make_user(status="pending")
        result = self._call(user)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_pending_has_approve_and_block(self):
        user = _make_user(uid=1, status="pending")
        result = self._call(user)
        cbs = _flat_cbs(result)
        assert any("approve_1" in cb for cb in cbs)
        assert any("block_1" in cb for cb in cbs)

    def test_approved_has_block_not_approve(self):
        user = _make_user(uid=2, status="approved", roles=["applicant"])
        result = self._call(user)
        cbs = _flat_cbs(result)
        assert any("block_2" in cb for cb in cbs)
        assert not any("approve_2" in cb for cb in cbs)

    def test_blocked_has_unblock(self):
        user = _make_user(uid=3, status="blocked", roles=["applicant"])
        result = self._call(user)
        cbs = _flat_cbs(result)
        assert any("unblock_3" in cb for cb in cbs)

    def test_executor_role_has_specializations_button(self):
        user = _make_user(uid=4, status="approved", roles=["executor"])
        result = self._call(user)
        cbs = _flat_cbs(result)
        assert any("user_specializations_4" in cb for cb in cbs)

    def test_non_executor_has_no_specializations_button(self):
        user = _make_user(uid=5, status="approved", roles=["applicant"])
        result = self._call(user)
        cbs = _flat_cbs(result)
        assert not any("user_specializations_5" in cb for cb in cbs)

    def test_back_to_list_callback(self):
        user = _make_user(status="pending")
        result = self._call(user)
        assert "user_mgmt_back_to_list" in _flat_cbs(result)


# ---------------------------------------------------------------------------
# get_roles_management_keyboard
# ---------------------------------------------------------------------------

class TestGetRolesManagementKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_roles_management_keyboard
            result = get_roles_management_keyboard(["applicant"])
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_two_save_cancel_buttons_at_end(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_roles_management_keyboard
            result = get_roles_management_keyboard([])
        cbs = _flat_cbs(result)
        assert "roles_save" in cbs
        assert "roles_cancel" in cbs

    def test_assigned_role_has_remove_action(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_roles_management_keyboard
            result = get_roles_management_keyboard(["executor"])
        cbs = _flat_cbs(result)
        assert any("role_remove_executor" in cb for cb in cbs)

    def test_unassigned_role_has_add_action(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_roles_management_keyboard
            result = get_roles_management_keyboard([])
        cbs = _flat_cbs(result)
        assert any("role_add_" in cb for cb in cbs)


# ---------------------------------------------------------------------------
# get_search_filters_keyboard
# ---------------------------------------------------------------------------

class TestGetSearchFiltersKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_search_filters_keyboard
            result = get_search_filters_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_six_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_search_filters_keyboard
            result = get_search_filters_keyboard()
        assert len(_flat_texts(result)) == 6

    def test_back_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_search_filters_keyboard
            result = get_search_filters_keyboard()
        assert "user_mgmt_main" in _flat_cbs(result)


# ---------------------------------------------------------------------------
# get_confirmation_keyboard
# ---------------------------------------------------------------------------

class TestGetConfirmationKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_confirmation_keyboard
            result = get_confirmation_keyboard("approve", 1)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_two_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_confirmation_keyboard
            result = get_confirmation_keyboard("block", 2)
        assert len(_flat_texts(result)) == 2

    def test_confirm_callback_contains_action_and_id(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_confirmation_keyboard
            result = get_confirmation_keyboard("approve", 7)
        cbs = _flat_cbs(result)
        assert "confirm_approve_7" in cbs


# ---------------------------------------------------------------------------
# get_cancel_keyboard
# ---------------------------------------------------------------------------

class TestGetCancelKeyboardUserMgmt:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_cancel_keyboard
            result = get_cancel_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_one_button(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_cancel_keyboard
            result = get_cancel_keyboard()
        assert len(_flat_texts(result)) == 1

    def test_cancel_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_cancel_keyboard
            result = get_cancel_keyboard()
        assert "user_mgmt_cancel" in _flat_cbs(result)


# ---------------------------------------------------------------------------
# get_specialization_stats_keyboard
# ---------------------------------------------------------------------------

class TestGetSpecializationStatsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_specialization_stats_keyboard
            result = get_specialization_stats_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_three_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.user_management import get_specialization_stats_keyboard
            result = get_specialization_stats_keyboard()
        assert len(_flat_texts(result)) == 3
