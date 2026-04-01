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

    def test_yes_button_has_role_switch_callback(self):
        from uk_management_bot.keyboards.base import get_executor_suggestion_inline
        result = get_executor_suggestion_inline(yes_text="Да", no_text="Нет")
        callbacks = [btn.callback_data for row in result.inline_keyboard for btn in row if btn.callback_data]
        assert any("executor" in c for c in callbacks)

    def test_no_button_has_skip_callback(self):
        from uk_management_bot.keyboards.base import get_executor_suggestion_inline
        result = get_executor_suggestion_inline(yes_text="Да", no_text="Нет")
        callbacks = [btn.callback_data for row in result.inline_keyboard for btn in row if btn.callback_data]
        assert "suggest_executor_skip" in callbacks


# ---------------------------------------------------------------------------
# Tests: get_yes_no_keyboard
# ---------------------------------------------------------------------------

class TestGetYesNoKeyboard:
    def test_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_yes_no_keyboard
            result = get_yes_no_keyboard()
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_has_three_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_yes_no_keyboard
            result = get_yes_no_keyboard()
        texts = _all_button_texts(result)
        assert len(texts) == 3

    def test_yes_button_present(self):
        mapping = {"buttons.yes": "Да", "buttons.no": "Нет", "buttons.back": "Назад"}
        with patch(GET_TEXT_PATH, side_effect=_make_get_text(mapping)):
            from uk_management_bot.keyboards.base import get_yes_no_keyboard
            result = get_yes_no_keyboard()
        assert "Да" in _all_button_texts(result)

    def test_no_button_present(self):
        mapping = {"buttons.yes": "Да", "buttons.no": "Нет", "buttons.back": "Назад"}
        with patch(GET_TEXT_PATH, side_effect=_make_get_text(mapping)):
            from uk_management_bot.keyboards.base import get_yes_no_keyboard
            result = get_yes_no_keyboard()
        assert "Нет" in _all_button_texts(result)

    def test_back_button_present(self):
        mapping = {"buttons.yes": "Да", "buttons.no": "Нет", "buttons.back": "Назад"}
        with patch(GET_TEXT_PATH, side_effect=_make_get_text(mapping)):
            from uk_management_bot.keyboards.base import get_yes_no_keyboard
            result = get_yes_no_keyboard()
        assert "Назад" in _all_button_texts(result)

    def test_language_uz_accepted(self):
        with patch(GET_TEXT_PATH, side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_yes_no_keyboard
            result = get_yes_no_keyboard(language="uz")
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_resize_keyboard_is_true(self):
        with patch(GET_TEXT_PATH, side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_yes_no_keyboard
            result = get_yes_no_keyboard()
        assert result.resize_keyboard is True


# ---------------------------------------------------------------------------
# Tests: get_user_contextual_keyboard
# ---------------------------------------------------------------------------

class TestGetUserContextualKeyboard:
    def test_user_found_returns_reply_keyboard(self):
        user = MagicMock()
        user.roles = ["executor"]
        user.active_role = "executor"
        user.role = None
        user.status = "approved"
        user.language = "ru"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = user

        with patch("uk_management_bot.database.session.SessionLocal", return_value=mock_db), \
             patch("uk_management_bot.keyboards.base.get_text", side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_user_contextual_keyboard
            result = get_user_contextual_keyboard(user_id=123)

        assert isinstance(result, ReplyKeyboardMarkup)

    def test_user_not_found_returns_default_keyboard(self):
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("uk_management_bot.database.session.SessionLocal", return_value=mock_db), \
             patch("uk_management_bot.keyboards.base.get_text", side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_user_contextual_keyboard
            result = get_user_contextual_keyboard(user_id=999)

        assert isinstance(result, ReplyKeyboardMarkup)

    def test_db_exception_returns_default_keyboard(self):
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("DB failure")

        with patch("uk_management_bot.database.session.SessionLocal", return_value=mock_db), \
             patch("uk_management_bot.keyboards.base.get_text", side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_user_contextual_keyboard
            result = get_user_contextual_keyboard(user_id=0)

        assert isinstance(result, ReplyKeyboardMarkup)

    def test_user_with_no_roles_but_legacy_role(self):
        """Falls back to user.role when user.roles is empty."""
        user = MagicMock()
        user.roles = None
        user.active_role = None
        user.role = "manager"
        user.status = "approved"
        user.language = "ru"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = user

        with patch("uk_management_bot.database.session.SessionLocal", return_value=mock_db), \
             patch("uk_management_bot.utils.auth_helpers.parse_roles_safe", return_value=[]), \
             patch("uk_management_bot.keyboards.base.get_text", side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_user_contextual_keyboard
            result = get_user_contextual_keyboard(user_id=456)

        assert isinstance(result, ReplyKeyboardMarkup)

    def test_user_with_pending_status(self):
        user = MagicMock()
        user.roles = ["applicant"]
        user.active_role = "applicant"
        user.role = None
        user.status = "pending"
        user.language = "ru"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = user

        mapping = {"main_menu.create_request": "Создать заявку"}
        with patch("uk_management_bot.database.session.SessionLocal", return_value=mock_db), \
             patch("uk_management_bot.keyboards.base.get_text", side_effect=_make_get_text(mapping)):
            from uk_management_bot.keyboards.base import get_user_contextual_keyboard
            result = get_user_contextual_keyboard(user_id=789)

        texts = _all_button_texts(result)
        assert "Создать заявку" not in texts


# ---------------------------------------------------------------------------
# Tests: get_main_keyboard_for_role — additional role combinations
# ---------------------------------------------------------------------------

class TestGetMainKeyboardForRoleExtended:
    """Additional branch coverage for get_main_keyboard_for_role."""

    def test_duplicate_roles_deduped(self):
        """Duplicate roles in list should not produce duplicate switch button."""
        mapping = {"main_menu.switch_role": "Сменить роль"}
        with patch(GET_TEXT_PATH, side_effect=_make_get_text(mapping)):
            from uk_management_bot.keyboards.base import get_main_keyboard_for_role
            result = get_main_keyboard_for_role("applicant", ["applicant", "applicant", "executor"])
        texts = _all_button_texts(result)
        switch_count = texts.count("Сменить роль")
        assert switch_count == 1

    def test_none_roles_list_no_switch_button(self):
        mapping = {"main_menu.switch_role": "Сменить роль"}
        with patch(GET_TEXT_PATH, side_effect=_make_get_text(mapping)):
            from uk_management_bot.keyboards.base import get_main_keyboard_for_role
            result = get_main_keyboard_for_role("applicant", None)
        texts = _all_button_texts(result)
        assert "Сменить роль" not in texts

    def test_approved_applicant_has_create_button(self):
        mapping = {"main_menu.create_request": "Создать заявку"}
        with patch(GET_TEXT_PATH, side_effect=_make_get_text(mapping)):
            from uk_management_bot.keyboards.base import get_main_keyboard_for_role
            result = get_main_keyboard_for_role(
                "applicant", ["applicant"], user_status="approved"
            )
        assert "Создать заявку" in _all_button_texts(result)

    def test_executor_multi_role_has_switch_button(self):
        mapping = {
            "main_menu.shift": "Смена",
            "main_menu.my_shifts": "Мои смены",
            "main_menu.switch_role": "Сменить роль",
        }
        with patch(GET_TEXT_PATH, side_effect=_make_get_text(mapping)):
            from uk_management_bot.keyboards.base import get_main_keyboard_for_role
            result = get_main_keyboard_for_role(
                "executor", ["executor", "manager"]
            )
        assert "Сменить роль" in _all_button_texts(result)

    def test_non_string_roles_filtered_out(self):
        """Non-string roles should be ignored (isinstance(r, str) guard)."""
        with patch(GET_TEXT_PATH, side_effect=_make_get_text()):
            from uk_management_bot.keyboards.base import get_main_keyboard_for_role
            # Pass a list with non-string mixed in
            result = get_main_keyboard_for_role("applicant", ["applicant", 123, None])
        assert isinstance(result, ReplyKeyboardMarkup)
