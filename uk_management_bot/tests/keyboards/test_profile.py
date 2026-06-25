"""
Unit tests for keyboards/profile.py

Tests return types and structure of all keyboard builder functions.
Locale strings are mocked so tests are independent of JSON locale files.
"""
from unittest.mock import patch, MagicMock

from aiogram.types import InlineKeyboardMarkup


GET_TEXT_PATH = "uk_management_bot.keyboards.profile.get_text"


def _flat_texts(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.text for row in markup.inline_keyboard for btn in row]


def _flat_cbs(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row]


def _echo(key: str, language: str = "ru", **kwargs) -> str:
    return key


# ---------------------------------------------------------------------------
# get_profile_edit_keyboard
# ---------------------------------------------------------------------------

class TestGetProfileEditKeyboard:
    def test_returns_inline_keyboard_markup_without_user(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.profile import get_profile_edit_keyboard
            result = get_profile_edit_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_returns_inline_keyboard_markup_with_user(self):
        user = MagicMock()
        user.phone = "+998991234567"
        user.first_name = "Иван"
        user.last_name = "Иванов"
        user.language = "ru"
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.profile import get_profile_edit_keyboard
            result = get_profile_edit_keyboard(user=user)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_six_buttons(self):
        """phone, language, first_name, last_name, my_apartments, cancel = 6."""
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.profile import get_profile_edit_keyboard
            result = get_profile_edit_keyboard()
        assert len(_flat_texts(result)) == 6

    def test_expected_callback_data_present(self):
        expected_cbs = {
            "edit_phone",
            "edit_language",
            "edit_first_name",
            "edit_last_name",
            "my_apartments",
            "cancel_profile_edit",
        }
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.profile import get_profile_edit_keyboard
            result = get_profile_edit_keyboard()
        assert set(_flat_cbs(result)) == expected_cbs

    def test_user_phone_in_button_text(self):
        """Phone button shows the user's actual phone number."""
        user = MagicMock()
        user.phone = "+998991234567"
        user.first_name = "Иван"
        user.last_name = "Иванов"
        user.language = "ru"
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.profile import get_profile_edit_keyboard
            result = get_profile_edit_keyboard(user=user)
        texts = _flat_texts(result)
        phone_btn = next(t for t in texts if _flat_cbs(result)[_flat_texts(result).index(t)] == "edit_phone")
        assert "+998991234567" in phone_btn

    def test_user_language_ru_shows_ru_flag(self):
        user = MagicMock()
        user.phone = None
        user.first_name = None
        user.last_name = None
        user.language = "ru"
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.profile import get_profile_edit_keyboard
            result = get_profile_edit_keyboard(user=user)
        texts = _flat_texts(result)
        lang_idx = _flat_cbs(result).index("edit_language")
        assert "🇷🇺" in texts[lang_idx]

    def test_user_language_uz_shows_uz_flag(self):
        user = MagicMock()
        user.phone = None
        user.first_name = None
        user.last_name = None
        user.language = "uz"
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.profile import get_profile_edit_keyboard
            result = get_profile_edit_keyboard(user=user)
        texts = _flat_texts(result)
        lang_idx = _flat_cbs(result).index("edit_language")
        assert "🇺🇿" in texts[lang_idx]

    def test_accepts_uz_language(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.profile import get_profile_edit_keyboard
            result = get_profile_edit_keyboard(language="uz")
        assert isinstance(result, InlineKeyboardMarkup)


# ---------------------------------------------------------------------------
# get_language_choice_keyboard
# ---------------------------------------------------------------------------

class TestGetLanguageChoiceKeyboard:
    def test_returns_inline_keyboard_markup_ru(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.profile import get_language_choice_keyboard
            result = get_language_choice_keyboard(language="ru")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_returns_inline_keyboard_markup_uz(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.profile import get_language_choice_keyboard
            result = get_language_choice_keyboard(language="uz")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_three_buttons(self):
        """Two language buttons + cancel."""
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.profile import get_language_choice_keyboard
            result = get_language_choice_keyboard()
        assert len(_flat_texts(result)) == 3

    def test_callback_data_for_language_options(self):
        expected_cbs = {"set_language_ru", "set_language_uz", "cancel_language_choice"}
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.profile import get_language_choice_keyboard
            result = get_language_choice_keyboard()
        assert set(_flat_cbs(result)) == expected_cbs


# ---------------------------------------------------------------------------
# get_address_type_keyboard
# ---------------------------------------------------------------------------

class TestGetAddressTypeKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.profile import get_address_type_keyboard
            result = get_address_type_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_four_buttons(self):
        """home, apartment, yard + cancel."""
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.profile import get_address_type_keyboard
            result = get_address_type_keyboard()
        assert len(_flat_texts(result)) == 4

    def test_callback_data_present(self):
        expected_cbs = {
            "address_type_home",
            "address_type_apartment",
            "address_type_yard",
            "cancel_address_type",
        }
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.profile import get_address_type_keyboard
            result = get_address_type_keyboard()
        assert set(_flat_cbs(result)) == expected_cbs


# ---------------------------------------------------------------------------
# get_cancel_keyboard (profile module)
# ---------------------------------------------------------------------------

class TestGetProfileCancelKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.profile import get_cancel_keyboard
            result = get_cancel_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_exactly_one_button(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.profile import get_cancel_keyboard
            result = get_cancel_keyboard()
        assert len(_flat_texts(result)) == 1

    def test_cancel_callback_data(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.profile import get_cancel_keyboard
            result = get_cancel_keyboard()
        assert _flat_cbs(result) == ["cancel_input"]
