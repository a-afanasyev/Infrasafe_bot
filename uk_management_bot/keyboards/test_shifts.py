"""
Unit tests for keyboards/shifts.py

Tests that all keyboard builder functions return the correct markup type
and have the expected structure (button counts, callback_data prefixes).
Locale strings are mocked so tests are independent of JSON locale files.
"""
import pytest
from unittest.mock import patch

from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup


GET_TEXT_PATH = "uk_management_bot.keyboards.shifts.get_text"


def _flat_reply(markup: ReplyKeyboardMarkup) -> list[str]:
    return [btn.text for row in markup.keyboard for btn in row]


def _flat_inline(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.text for row in markup.inline_keyboard for btn in row]


def _flat_inline_cbs(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row]


def _echo_get_text(key: str, language: str = "ru", **kwargs) -> str:
    """Return key as text so button structure is deterministic without locale files."""
    return key


# ---------------------------------------------------------------------------
# get_shifts_main_keyboard
# ---------------------------------------------------------------------------

class TestGetShiftsMainKeyboard:
    def test_returns_reply_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_shifts_main_keyboard
            result = get_shifts_main_keyboard()
        assert isinstance(result, ReplyKeyboardMarkup)

    def test_resize_keyboard(self):
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_shifts_main_keyboard
            result = get_shifts_main_keyboard()
        assert result.resize_keyboard is True

    def test_has_five_buttons(self):
        """Shift main keyboard has accept, end, my_shift, history and back."""
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_shifts_main_keyboard
            result = get_shifts_main_keyboard()
        assert len(_flat_reply(result)) == 5

    def test_buttons_use_expected_text_keys(self):
        """Button texts come from expected locale keys."""
        expected_keys = {
            "shifts.accept_shift",
            "shifts.end_shift",
            "shifts.my_shift",
            "shifts.shift_history",
            "buttons.back",
        }
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_shifts_main_keyboard
            result = get_shifts_main_keyboard()
        texts = set(_flat_reply(result))
        assert texts == expected_keys

    def test_accepts_uz_language(self):
        """Keyboard can be built for Uzbek without errors."""
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_shifts_main_keyboard
            result = get_shifts_main_keyboard(language="uz")
        assert isinstance(result, ReplyKeyboardMarkup)


# ---------------------------------------------------------------------------
# get_end_shift_confirm_inline
# ---------------------------------------------------------------------------

class TestGetEndShiftConfirmInline:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_end_shift_confirm_inline
            result = get_end_shift_confirm_inline()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_two_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_end_shift_confirm_inline
            result = get_end_shift_confirm_inline()
        assert len(_flat_inline(result)) == 2

    def test_callback_data_values(self):
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_end_shift_confirm_inline
            result = get_end_shift_confirm_inline()
        cbs = _flat_inline_cbs(result)
        assert "shift_end_confirm_yes" in cbs
        assert "shift_end_confirm_no" in cbs


# ---------------------------------------------------------------------------
# get_shifts_filters_inline
# ---------------------------------------------------------------------------

class TestGetShiftsFiltersInline:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_shifts_filters_inline
            result = get_shifts_filters_inline()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_period_and_status_rows_plus_reset(self):
        """5 period rows + 4 status rows + 1 reset row = 10 buttons total."""
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_shifts_filters_inline
            result = get_shifts_filters_inline()
        assert len(_flat_inline(result)) == 10

    def test_active_period_marked(self):
        """Selected period button text starts with bullet marker '• '."""
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_shifts_filters_inline
            result = get_shifts_filters_inline(period="today")
        texts = _flat_inline(result)
        today_btn = next(t for t in texts if "today" in t)
        assert today_btn.startswith("• ")

    def test_active_status_marked(self):
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_shifts_filters_inline
            result = get_shifts_filters_inline(status="active")
        texts = _flat_inline(result)
        active_btn = next(t for t in texts if "active" in t)
        assert active_btn.startswith("• ")

    def test_reset_callback_data(self):
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_shifts_filters_inline
            result = get_shifts_filters_inline()
        cbs = _flat_inline_cbs(result)
        assert "shifts_filters_reset" in cbs

    def test_period_callback_data_prefix(self):
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_shifts_filters_inline
            result = get_shifts_filters_inline()
        cbs = _flat_inline_cbs(result)
        period_cbs = [c for c in cbs if c.startswith("shifts_period_")]
        assert len(period_cbs) == 5

    def test_status_callback_data_prefix(self):
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_shifts_filters_inline
            result = get_shifts_filters_inline()
        cbs = _flat_inline_cbs(result)
        status_cbs = [c for c in cbs if c.startswith("shifts_status_")]
        assert len(status_cbs) == 4


# ---------------------------------------------------------------------------
# get_pagination_inline
# ---------------------------------------------------------------------------

class TestGetPaginationInline:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_pagination_inline
            result = get_pagination_inline(current_page=1, total_pages=5)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_first_page_no_prev_button(self):
        """First page should have no prev button — only indicator + next."""
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_pagination_inline
            result = get_pagination_inline(current_page=1, total_pages=5)
        cbs = _flat_inline_cbs(result)
        assert not any(c.startswith("shifts_page_0") for c in cbs)
        assert "shifts_page_2" in cbs

    def test_last_page_no_next_button(self):
        """Last page should have no next button — only prev + indicator."""
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_pagination_inline
            result = get_pagination_inline(current_page=5, total_pages=5)
        cbs = _flat_inline_cbs(result)
        assert not any(c.startswith("shifts_page_6") for c in cbs)
        assert "shifts_page_4" in cbs

    def test_middle_page_has_prev_and_next(self):
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_pagination_inline
            result = get_pagination_inline(current_page=3, total_pages=5)
        cbs = _flat_inline_cbs(result)
        assert "shifts_page_2" in cbs
        assert "shifts_page_4" in cbs

    def test_single_page_only_indicator(self):
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_pagination_inline
            result = get_pagination_inline(current_page=1, total_pages=1)
        assert len(_flat_inline(result)) == 1


# ---------------------------------------------------------------------------
# get_manager_active_shifts_row
# ---------------------------------------------------------------------------

class TestGetManagerActiveShiftsRow:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_manager_active_shifts_row
            result = get_manager_active_shifts_row(telegram_id=12345)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_one_button(self):
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_manager_active_shifts_row
            result = get_manager_active_shifts_row(telegram_id=12345)
        assert len(_flat_inline(result)) == 1

    def test_callback_data_contains_telegram_id(self):
        with patch(GET_TEXT_PATH, side_effect=_echo_get_text):
            from uk_management_bot.keyboards.shifts import get_manager_active_shifts_row
            result = get_manager_active_shifts_row(telegram_id=99999)
        cbs = _flat_inline_cbs(result)
        assert cbs[0] == "force_end_shift_99999"
