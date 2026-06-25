"""
Unit tests for keyboards/request_comments.py

Tests each builder returns InlineKeyboardMarkup with correct buttons.
get_text and RequestCallbackHelper are mocked.
"""
import pytest
from unittest.mock import patch
from aiogram.types import InlineKeyboardMarkup


GET_TEXT_PATH = "uk_management_bot.keyboards.request_comments.get_text"
CALLBACK_HELPER_PATH = "uk_management_bot.keyboards.request_comments.RequestCallbackHelper"


def _mock_get_text(key: str, language: str = "ru", **kwargs) -> str:
    return key


def _mock_callback(prefix: str, request_number: str) -> str:
    return f"{prefix}{request_number}"


def _all_buttons(markup: InlineKeyboardMarkup) -> list:
    return [btn for row in markup.inline_keyboard for btn in row]


def _all_callbacks(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.callback_data for btn in _all_buttons(markup) if btn.callback_data]


# ---------------------------------------------------------------------------
# get_comment_type_keyboard
# ---------------------------------------------------------------------------

class TestGetCommentTypeKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_comments import get_comment_type_keyboard
            result = get_comment_type_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_five_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_comments import get_comment_type_keyboard
            result = get_comment_type_keyboard()
        assert len(_all_buttons(result)) == 5

    def test_cancel_callback_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_comments import get_comment_type_keyboard
            result = get_comment_type_keyboard()
        assert "cancel_comment" in _all_callbacks(result)

    def test_general_type_callback_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_comments import get_comment_type_keyboard
            result = get_comment_type_keyboard()
        assert "comment_type_general" in _all_callbacks(result)

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_language_accepted(self, language):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_comments import get_comment_type_keyboard
            result = get_comment_type_keyboard(language=language)
        assert isinstance(result, InlineKeyboardMarkup)


# ---------------------------------------------------------------------------
# get_comment_confirmation_keyboard
# ---------------------------------------------------------------------------

class TestGetCommentConfirmationKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_comments import get_comment_confirmation_keyboard
            result = get_comment_confirmation_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_two_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_comments import get_comment_confirmation_keyboard
            result = get_comment_confirmation_keyboard()
        assert len(_all_buttons(result)) == 2

    def test_confirm_and_cancel_callbacks(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_comments import get_comment_confirmation_keyboard
            result = get_comment_confirmation_keyboard()
        callbacks = set(_all_callbacks(result))
        assert "confirm_comment" in callbacks
        assert "cancel_comment" in callbacks


# ---------------------------------------------------------------------------
# get_comments_list_keyboard
# ---------------------------------------------------------------------------

class TestGetCommentsListKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text), \
             patch(CALLBACK_HELPER_PATH + ".create_callback_data_with_request_number", side_effect=_mock_callback):
            from uk_management_bot.keyboards.request_comments import get_comments_list_keyboard
            result = get_comments_list_keyboard("250101-001")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_five_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text), \
             patch(CALLBACK_HELPER_PATH + ".create_callback_data_with_request_number", side_effect=_mock_callback):
            from uk_management_bot.keyboards.request_comments import get_comments_list_keyboard
            result = get_comments_list_keyboard("250101-001")
        assert len(_all_buttons(result)) == 5

    def test_add_comment_callback_contains_request_number(self):
        rn = "250101-002"
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text), \
             patch(CALLBACK_HELPER_PATH + ".create_callback_data_with_request_number", side_effect=_mock_callback):
            from uk_management_bot.keyboards.request_comments import get_comments_list_keyboard
            result = get_comments_list_keyboard(rn)
        callbacks = _all_callbacks(result)
        assert any(rn in c for c in callbacks)


# ---------------------------------------------------------------------------
# get_comment_actions_keyboard
# ---------------------------------------------------------------------------

class TestGetCommentActionsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_comments import get_comment_actions_keyboard
            result = get_comment_actions_keyboard("250101-003", comment_id=42)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_two_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_comments import get_comment_actions_keyboard
            result = get_comment_actions_keyboard("250101-003", comment_id=42)
        assert len(_all_buttons(result)) == 2

    def test_reply_callback_contains_comment_id(self):
        comment_id = 99
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_comments import get_comment_actions_keyboard
            result = get_comment_actions_keyboard("250101-004", comment_id=comment_id)
        callbacks = _all_callbacks(result)
        assert any(str(comment_id) in c for c in callbacks)

    def test_back_callback_contains_request_number(self):
        rn = "250101-005"
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_comments import get_comment_actions_keyboard
            result = get_comment_actions_keyboard(rn, comment_id=1)
        callbacks = _all_callbacks(result)
        assert any(rn in c for c in callbacks)
