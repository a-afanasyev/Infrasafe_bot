"""
Unit tests for keyboards/requests.py

Tests return types, button counts, and callback-data conventions.
get_text is mocked; DB/service calls that happen inside keyboard functions
(yard/building/apartment selection) are also patched.
"""
import pytest
from unittest.mock import patch

from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup

GET_TEXT_PATH = "uk_management_bot.keyboards.requests.get_text"


def _echo(key: str, language: str = "ru", **kwargs) -> str:
    return key


def _flat_reply_texts(markup: ReplyKeyboardMarkup) -> list[str]:
    return [btn.text for row in markup.keyboard for btn in row]


def _flat_inline_texts(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.text for row in markup.inline_keyboard for btn in row]


def _flat_inline_cbs(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row]


# ---------------------------------------------------------------------------
# get_categories_keyboard
# ---------------------------------------------------------------------------

class TestGetCategoriesKeyboard:
    def test_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_categories_keyboard
            result = get_categories_keyboard()
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_resize_keyboard_true(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_categories_keyboard
            result = get_categories_keyboard()
        assert result.resize_keyboard is True

    def test_has_nine_buttons(self):
        """8 categories (2 per row = 4 rows) + 1 cancel row = 9 buttons total."""
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_categories_keyboard
            result = get_categories_keyboard()
        assert len(_flat_reply_texts(result)) == 9


# ---------------------------------------------------------------------------
# get_categories_inline_keyboard
# ---------------------------------------------------------------------------

class TestGetCategoriesInlineKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_categories_inline_keyboard
            result = get_categories_inline_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_eight_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_categories_inline_keyboard
            result = get_categories_inline_keyboard()
        assert len(_flat_inline_texts(result)) == 8

    def test_callbacks_use_category_prefix(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_categories_inline_keyboard, CALLBACK_PREFIX_CATEGORY
            result = get_categories_inline_keyboard()
        cbs = _flat_inline_cbs(result)
        assert all(cb.startswith(CALLBACK_PREFIX_CATEGORY) for cb in cbs)


# ---------------------------------------------------------------------------
# get_categories_inline_keyboard_with_cancel
# ---------------------------------------------------------------------------

class TestGetCategoriesInlineKeyboardWithCancel:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_categories_inline_keyboard_with_cancel
            result = get_categories_inline_keyboard_with_cancel()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_nine_buttons(self):
        """8 category buttons + 1 cancel = 9 total."""
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_categories_inline_keyboard_with_cancel
            result = get_categories_inline_keyboard_with_cancel()
        assert len(_flat_inline_texts(result)) == 9

    def test_cancel_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_categories_inline_keyboard_with_cancel
            result = get_categories_inline_keyboard_with_cancel()
        assert "cancel_create" in _flat_inline_cbs(result)


# ---------------------------------------------------------------------------
# get_urgency_keyboard
# ---------------------------------------------------------------------------

class TestGetUrgencyKeyboard:
    def test_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_urgency_keyboard
            result = get_urgency_keyboard()
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_has_five_buttons(self):
        """4 urgency levels + 1 cancel = 5."""
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_urgency_keyboard
            result = get_urgency_keyboard()
        assert len(_flat_reply_texts(result)) == 5


# ---------------------------------------------------------------------------
# get_urgency_inline_keyboard
# ---------------------------------------------------------------------------

class TestGetUrgencyInlineKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_urgency_inline_keyboard
            result = get_urgency_inline_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_four_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_urgency_inline_keyboard
            result = get_urgency_inline_keyboard()
        assert len(_flat_inline_texts(result)) == 4

    def test_callbacks_use_urgency_prefix(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_urgency_inline_keyboard, CALLBACK_PREFIX_URGENCY
            result = get_urgency_inline_keyboard()
        cbs = _flat_inline_cbs(result)
        assert all(cb.startswith(CALLBACK_PREFIX_URGENCY) for cb in cbs)


# ---------------------------------------------------------------------------
# get_cancel_keyboard
# ---------------------------------------------------------------------------

class TestGetRequestsCancelKeyboard:
    def test_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_cancel_keyboard
            result = get_cancel_keyboard()
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_has_one_button(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_cancel_keyboard
            result = get_cancel_keyboard()
        assert len(_flat_reply_texts(result)) == 1


# ---------------------------------------------------------------------------
# get_media_keyboard
# ---------------------------------------------------------------------------

class TestGetMediaKeyboard:
    def test_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_media_keyboard
            result = get_media_keyboard()
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_has_two_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_media_keyboard
            result = get_media_keyboard()
        assert len(_flat_reply_texts(result)) == 2


# ---------------------------------------------------------------------------
# get_confirmation_keyboard
# ---------------------------------------------------------------------------

class TestGetRequestsConfirmationKeyboard:
    def test_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_confirmation_keyboard
            result = get_confirmation_keyboard()
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_has_three_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_confirmation_keyboard
            result = get_confirmation_keyboard()
        assert len(_flat_reply_texts(result)) == 3


# ---------------------------------------------------------------------------
# get_inline_confirmation_keyboard
# ---------------------------------------------------------------------------

class TestGetInlineConfirmationKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_inline_confirmation_keyboard
            result = get_inline_confirmation_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_two_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_inline_confirmation_keyboard
            result = get_inline_confirmation_keyboard()
        assert len(_flat_inline_texts(result)) == 2

    def test_confirm_yes_and_confirm_no_callbacks(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_inline_confirmation_keyboard
            result = get_inline_confirmation_keyboard()
        cbs = _flat_inline_cbs(result)
        assert "confirm_yes" in cbs
        assert "confirm_no" in cbs


# ---------------------------------------------------------------------------
# get_edit_request_keyboard
# ---------------------------------------------------------------------------

class TestGetEditRequestKeyboard:
    @pytest.mark.xfail(
        reason="BUG: get_edit_request_keyboard passes raw strings as row entries "
               "instead of KeyboardButton objects — aiogram Pydantic raises ValidationError. "
               "Source code needs wrapping each entry in KeyboardButton(text=...).",
        strict=True,
    )
    def test_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_edit_request_keyboard
            result = get_edit_request_keyboard()
        assert isinstance(result, ReplyKeyboardMarkup)


# ---------------------------------------------------------------------------
# get_request_status_keyboard
# ---------------------------------------------------------------------------

class TestGetRequestStatusKeyboard:
    @pytest.mark.xfail(
        reason="BUG: get_request_status_keyboard passes raw strings as row entries "
               "instead of KeyboardButton objects — same bug as get_edit_request_keyboard.",
        strict=True,
    )
    def test_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_request_status_keyboard
            result = get_request_status_keyboard()
        assert isinstance(result, ReplyKeyboardMarkup)


# ---------------------------------------------------------------------------
# get_requests_filter_keyboard
# ---------------------------------------------------------------------------

class TestGetRequestsFilterKeyboard:
    @pytest.mark.xfail(
        reason="BUG: get_requests_filter_keyboard passes raw strings as row entries "
               "instead of KeyboardButton objects — same bug as get_edit_request_keyboard.",
        strict=True,
    )
    def test_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_requests_filter_keyboard
            result = get_requests_filter_keyboard()
        assert isinstance(result, ReplyKeyboardMarkup)


# ---------------------------------------------------------------------------
# get_pagination_keyboard
# ---------------------------------------------------------------------------

class TestGetPaginationKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_pagination_keyboard
            result = get_pagination_keyboard(1, 3)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_first_page_has_no_prev(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_pagination_keyboard
            result = get_pagination_keyboard(1, 5)
        cbs = _flat_inline_cbs(result)
        # Only indicator + next
        assert not any(cb == "page_0" for cb in cbs)
        assert any(cb == "page_2" for cb in cbs)

    def test_last_page_has_no_next(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_pagination_keyboard
            result = get_pagination_keyboard(5, 5)
        cbs = _flat_inline_cbs(result)
        assert not any(cb == "page_6" for cb in cbs)

    def test_middle_page_has_prev_and_next(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_pagination_keyboard
            result = get_pagination_keyboard(3, 5)
        cbs = _flat_inline_cbs(result)
        assert "page_2" in cbs
        assert "page_4" in cbs

    def test_with_request_number_shows_action_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_pagination_keyboard
            result = get_pagination_keyboard(1, 1, request_number="260101-001")
        texts = _flat_inline_texts(result)
        # Should have more than just the page indicator
        assert len(texts) > 1

    def test_page_indicator_text(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_pagination_keyboard
            result = get_pagination_keyboard(2, 4)
        texts = _flat_inline_texts(result)
        assert "2/4" in texts


# ---------------------------------------------------------------------------
# get_request_actions_keyboard
# ---------------------------------------------------------------------------

class TestGetRequestActionsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_request_actions_keyboard
            result = get_request_actions_keyboard("260101-001")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_ten_buttons(self):
        """2+2+2+2+1+1 = 10 action buttons."""
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_request_actions_keyboard
            result = get_request_actions_keyboard("260101-001")
        assert len(_flat_inline_texts(result)) == 10

    def test_callbacks_not_empty(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_request_actions_keyboard
            result = get_request_actions_keyboard("260101-001")
        cbs = _flat_inline_cbs(result)
        assert all(cb for cb in cbs)


# ---------------------------------------------------------------------------
# Helper functions: get_category_display, resolve_category_key
# ---------------------------------------------------------------------------

class TestGetCategoryDisplay:
    def test_known_key_returns_localized(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_category_display
            result = get_category_display("electricity")
        assert result == "categories.electricity"

    def test_unknown_key_returns_as_is(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.requests import get_category_display
            result = get_category_display("unknown_cat")
        assert result == "unknown_cat"


class TestResolveCategoryKey:
    def test_internal_key_passthrough(self):
        from uk_management_bot.keyboards.requests import resolve_category_key
        assert resolve_category_key("electricity") == "electricity"

    def test_legacy_text_resolved(self):
        from uk_management_bot.keyboards.requests import resolve_category_key
        assert resolve_category_key("Электрика") == "electricity"

    def test_unknown_value_returned_as_is(self):
        from uk_management_bot.keyboards.requests import resolve_category_key
        assert resolve_category_key("НеизвестноеЗначение") == "НеизвестноеЗначение"

    def test_internet_legacy_text(self):
        from uk_management_bot.keyboards.requests import resolve_category_key
        assert resolve_category_key("Интернет/ТВ") == "internet"
