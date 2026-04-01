"""
Unit tests for keyboards/base.py

Tests that keyboard builder functions return correct markup types and
contain buttons driven by role/status logic, without relying on specific
locale strings.
"""
import pytest
from unittest.mock import patch, MagicMock

from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_button_texts(markup: ReplyKeyboardMarkup) -> list[str]:
    """Flatten all button texts from a ReplyKeyboardMarkup into a list."""
    return [btn.text for row in markup.keyboard for btn in row]


def _all_inline_texts(markup: InlineKeyboardMarkup) -> list[str]:
    """Flatten all button texts from an InlineKeyboardMarkup into a list."""
    return [btn.text for row in markup.inline_keyboard for btn in row]


# ---------------------------------------------------------------------------
# Patch target: get_text is imported directly inside keyboards/base.py
# ---------------------------------------------------------------------------
GET_TEXT_PATH = "uk_management_bot.keyboards.base.get_text"


def _make_get_text(mapping: dict | None = None):
    """
    Return a side_effect for get_text that either looks up from *mapping*
    or echoes the key as a plain string.  This keeps tests independent of
    the actual locale JSON files.
    """
    def _get_text(key: str, language: str = "ru", **kwargs) -> str:
        if mapping and key in mapping:
            return mapping[key]
        return key  # echo the key
    return _get_text


# ---------------------------------------------------------------------------
# Tests: get_main_keyboard
# ---------------------------------------------------------------------------

class TestGetMainKeyboard:
    def test_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_main_keyboard
            result = get_main_keyboard()
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_resize_keyboard_is_true(self):
        with patch(GET_TEXT_PATH, side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_main_keyboard
            result = get_main_keyboard()
        assert result.resize_keyboard is True

    def test_has_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_main_keyboard
            result = get_main_keyboard()
        assert len(_all_button_texts(result)) > 0


# ---------------------------------------------------------------------------
# Tests: get_main_keyboard_for_role
# ---------------------------------------------------------------------------

class TestGetMainKeyboardForRole:
    """get_main_keyboard_for_role returns correct buttons per active role."""

    def test_returns_reply_keyboard_markup_for_applicant(self):
        with patch(GET_TEXT_PATH, side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_main_keyboard_for_role
            result = get_main_keyboard_for_role("applicant", ["applicant"])
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_applicant_has_create_request_button(self):
        """Applicant keyboard must include the 'create request' button."""
        mapping = {"main_menu.create_request": "Создать заявку"}
        with patch(GET_TEXT_PATH, side_effect=_make_get_text(mapping)):
            from uk_management_bot.keyboards.base import get_main_keyboard_for_role
            result = get_main_keyboard_for_role("applicant", ["applicant"])
        texts = _all_button_texts(result)
        assert "Создать заявку" in texts

    def test_executor_has_shift_buttons(self):
        """Executor keyboard must include shift-related buttons."""
        mapping = {
            "main_menu.shift": "Смена",
            "main_menu.my_shifts": "Мои смены",
        }
        with patch(GET_TEXT_PATH, side_effect=_make_get_text(mapping)):
            from uk_management_bot.keyboards.base import get_main_keyboard_for_role
            result = get_main_keyboard_for_role("executor", ["executor"])
        texts = _all_button_texts(result)
        assert "Смена" in texts
        assert "Мои смены" in texts

    def test_executor_has_no_create_request_button(self):
        """Executor keyboard must NOT include the applicant 'create request' button."""
        mapping = {"main_menu.create_request": "Создать заявку"}
        with patch(GET_TEXT_PATH, side_effect=_make_get_text(mapping)):
            from uk_management_bot.keyboards.base import get_main_keyboard_for_role
            result = get_main_keyboard_for_role("executor", ["executor"])
        texts = _all_button_texts(result)
        assert "Создать заявку" not in texts

    def test_manager_has_admin_panel_button(self):
        """Manager keyboard must include the admin panel button."""
        mapping = {"main_menu.admin_panel": "Панель администратора"}
        with patch(GET_TEXT_PATH, side_effect=_make_get_text(mapping)):
            from uk_management_bot.keyboards.base import get_main_keyboard_for_role
            result = get_main_keyboard_for_role("manager", ["manager"])
        texts = _all_button_texts(result)
        assert "Панель администратора" in texts

    def test_admin_has_admin_panel_button(self):
        """Admin active role also receives the admin panel button."""
        mapping = {"main_menu.admin_panel": "Панель администратора"}
        with patch(GET_TEXT_PATH, side_effect=_make_get_text(mapping)):
            from uk_management_bot.keyboards.base import get_main_keyboard_for_role
            result = get_main_keyboard_for_role("admin", ["admin"])
        texts = _all_button_texts(result)
        assert "Панель администратора" in texts

    def test_pending_user_has_no_create_request_button(self):
        """Pending applicants must NOT see the 'create request' button."""
        mapping = {"main_menu.create_request": "Создать заявку"}
        with patch(GET_TEXT_PATH, side_effect=_make_get_text(mapping)):
            from uk_management_bot.keyboards.base import get_main_keyboard_for_role
            result = get_main_keyboard_for_role(
                "applicant", ["applicant"], user_status="pending"
            )
        texts = _all_button_texts(result)
        assert "Создать заявку" not in texts

    def test_multi_role_has_switch_role_button(self):
        """Users with multiple roles must see a role-switch button."""
        mapping = {"main_menu.switch_role": "Сменить роль"}
        with patch(GET_TEXT_PATH, side_effect=_make_get_text(mapping)):
            from uk_management_bot.keyboards.base import get_main_keyboard_for_role
            result = get_main_keyboard_for_role(
                "applicant", ["applicant", "executor"]
            )
        texts = _all_button_texts(result)
        assert "Сменить роль" in texts

    def test_single_role_has_no_switch_role_button(self):
        """Users with a single role must NOT see a role-switch button."""
        mapping = {"main_menu.switch_role": "Сменить роль"}
        with patch(GET_TEXT_PATH, side_effect=_make_get_text(mapping)):
            from uk_management_bot.keyboards.base import get_main_keyboard_for_role
            result = get_main_keyboard_for_role("applicant", ["applicant"])
        texts = _all_button_texts(result)
        assert "Сменить роль" not in texts


# ---------------------------------------------------------------------------
# Tests: get_cancel_keyboard
# ---------------------------------------------------------------------------

class TestGetCancelKeyboard:
    def test_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_cancel_keyboard
            result = get_cancel_keyboard()
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_has_exactly_one_button(self):
        with patch(GET_TEXT_PATH, side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_cancel_keyboard
            result = get_cancel_keyboard()
        assert len(_all_button_texts(result)) == 1


# ---------------------------------------------------------------------------
# Tests: get_contextual_keyboard
# ---------------------------------------------------------------------------

class TestGetContextualKeyboard:
    def test_no_roles_returns_reply_keyboard_markup(self):
        """With no roles/active_role, falls back to default keyboard."""
        with patch(GET_TEXT_PATH, side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_contextual_keyboard
            result = get_contextual_keyboard()
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_none_roles_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_contextual_keyboard
            result = get_contextual_keyboard(roles=None, active_role=None)
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_with_roles_delegates_to_role_keyboard(self):
        """With roles provided, returns same type as get_main_keyboard_for_role."""
        with patch(GET_TEXT_PATH, side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_contextual_keyboard
            result = get_contextual_keyboard(
                roles=["executor"], active_role="executor"
            )
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_empty_roles_list_returns_default(self):
        with patch(GET_TEXT_PATH, side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_contextual_keyboard
            result = get_contextual_keyboard(roles=[], active_role=None)
        assert isinstance(result, ReplyKeyboardMarkup)


# ---------------------------------------------------------------------------
# Tests: get_rating_keyboard
# ---------------------------------------------------------------------------

class TestGetRatingKeyboard:
    def test_returns_inline_keyboard_markup(self):
        from uk_management_bot.keyboards.base import get_rating_keyboard
        result = get_rating_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_five_buttons(self):
        from uk_management_bot.keyboards.base import get_rating_keyboard
        result = get_rating_keyboard()
        assert len(_all_inline_texts(result)) == 5


# ---------------------------------------------------------------------------
# Tests: get_role_switch_inline
# ---------------------------------------------------------------------------

class TestGetRoleSwitchInline:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_role_switch_inline
            result = get_role_switch_inline(
                roles=["applicant", "executor"], active_role="applicant"
            )
        assert isinstance(result, InlineKeyboardMarkup)

    def test_button_count_matches_roles(self):
        with patch(GET_TEXT_PATH, side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_role_switch_inline
            roles = ["applicant", "executor", "manager"]
            result = get_role_switch_inline(roles=roles, active_role="applicant")
        assert len(_all_inline_texts(result)) == len(roles)

    def test_active_role_marked_with_checkmark(self):
        """Active role button text must contain the checkmark marker."""
        mapping = {"roles.executor": "Исполнитель", "roles.applicant": "Заявитель"}
        with patch(GET_TEXT_PATH, side_effect=_make_get_text(mapping)):
            from uk_management_bot.keyboards.base import get_role_switch_inline
            result = get_role_switch_inline(
                roles=["applicant", "executor"], active_role="executor"
            )
        texts = _all_inline_texts(result)
        executor_btn = next(t for t in texts if "Исполнитель" in t)
        assert "✓" in executor_btn


# ---------------------------------------------------------------------------
# Tests: get_executor_suggestion_inline
# ---------------------------------------------------------------------------

class TestGetExecutorSuggestionInline:
    def test_returns_inline_keyboard_markup(self):
        from uk_management_bot.keyboards.base import get_executor_suggestion_inline
        result = get_executor_suggestion_inline(yes_text="Да", no_text="Нет")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_two_buttons(self):
        from uk_management_bot.keyboards.base import get_executor_suggestion_inline
        result = get_executor_suggestion_inline(yes_text="Да", no_text="Нет")
        assert len(_all_inline_texts(result)) == 2
