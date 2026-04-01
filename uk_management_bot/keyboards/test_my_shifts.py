"""
Unit tests for keyboards/my_shifts.py

Tests return types, button counts, and callback-data structure.
get_text is mocked; Shift objects are created via MagicMock.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, date, timedelta

from aiogram.types import InlineKeyboardMarkup

GET_TEXT_PATH = "uk_management_bot.keyboards.my_shifts.get_text"


def _echo(key: str, language: str = "ru", **kwargs) -> str:
    return key


def _flat_texts(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.text for row in markup.inline_keyboard for btn in row]


def _flat_cbs(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row]


def _make_shift(shift_id: int = 1, status: str = "planned",
                specialization_focus: list | None = None,
                planned_start: datetime | None = None,
                planned_end: datetime | None = None) -> MagicMock:
    shift = MagicMock()
    shift.id = shift_id
    shift.status = status
    shift.specialization_focus = specialization_focus or []
    shift.planned_start_time = planned_start or datetime(2026, 1, 1, 9, 0)
    shift.planned_end_time = planned_end or datetime(2026, 1, 1, 18, 0)
    return shift


# ---------------------------------------------------------------------------
# get_my_shifts_menu
# ---------------------------------------------------------------------------

class TestGetMyShiftsMenu:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_my_shifts_menu
            result = get_my_shifts_menu()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_six_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_my_shifts_menu
            result = get_my_shifts_menu()
        assert len(_flat_texts(result)) == 6

    def test_view_current_shifts_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_my_shifts_menu
            result = get_my_shifts_menu()
        assert "view_current_shifts" in _flat_cbs(result)

    def test_shift_transfer_menu_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_my_shifts_menu
            result = get_my_shifts_menu()
        assert "shift_transfer_menu" in _flat_cbs(result)


# ---------------------------------------------------------------------------
# get_shift_list_keyboard
# ---------------------------------------------------------------------------

class TestGetShiftListKeyboard:
    def test_returns_inline_keyboard_markup(self):
        shifts = [_make_shift(1), _make_shift(2)]
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_list_keyboard
            result = get_shift_list_keyboard(shifts)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_one_button_per_shift_plus_two_nav_buttons(self):
        shifts = [_make_shift(i) for i in range(3)]
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_list_keyboard
            result = get_shift_list_keyboard(shifts)
        # 3 shift buttons + refresh + back
        assert len(_flat_texts(result)) == 5

    def test_empty_shifts_has_nav_buttons_only(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_list_keyboard
            result = get_shift_list_keyboard([])
        assert len(_flat_texts(result)) == 2

    def test_shift_button_callback_contains_id(self):
        shift = _make_shift(shift_id=7)
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_list_keyboard
            result = get_shift_list_keyboard([shift])
        cbs = _flat_cbs(result)
        assert any("shift_details:7" in cb for cb in cbs)

    def test_back_to_my_shifts_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_list_keyboard
            result = get_shift_list_keyboard([])
        assert "back_to_my_shifts" in _flat_cbs(result)


# ---------------------------------------------------------------------------
# get_shift_actions_keyboard
# ---------------------------------------------------------------------------

class TestGetShiftActionsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        shift = _make_shift(status="planned")
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_actions_keyboard
            result = get_shift_actions_keyboard(shift)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_planned_has_start_shift(self):
        shift = _make_shift(status="planned")
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_actions_keyboard
            result = get_shift_actions_keyboard(shift)
        assert "start_shift" in _flat_cbs(result)

    def test_planned_has_transfer_and_decline(self):
        shift = _make_shift(shift_id=3, status="planned")
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_actions_keyboard
            result = get_shift_actions_keyboard(shift)
        cbs = _flat_cbs(result)
        assert any("transfer_shift:3" in cb for cb in cbs)
        assert any("decline_shift:3" in cb for cb in cbs)

    def test_active_has_end_shift(self):
        shift = _make_shift(status="active")
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_actions_keyboard
            result = get_shift_actions_keyboard(shift)
        assert "end_shift" in _flat_cbs(result)

    def test_active_has_take_break(self):
        shift = _make_shift(status="active")
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_actions_keyboard
            result = get_shift_actions_keyboard(shift)
        assert "take_break" in _flat_cbs(result)

    def test_completed_has_shift_report(self):
        shift = _make_shift(shift_id=5, status="completed")
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_actions_keyboard
            result = get_shift_actions_keyboard(shift)
        cbs = _flat_cbs(result)
        assert any("view_shift_report:5" in cb for cb in cbs)

    def test_back_to_list_callback_always_present(self):
        for status in ("planned", "active", "completed", "cancelled"):
            shift = _make_shift(status=status)
            with patch(GET_TEXT_PATH, side_effect=_echo):
                from uk_management_bot.keyboards.my_shifts import get_shift_actions_keyboard
                result = get_shift_actions_keyboard(shift)
            assert "view_current_shifts" in _flat_cbs(result)


# ---------------------------------------------------------------------------
# get_shift_filter_keyboard
# ---------------------------------------------------------------------------

class TestGetShiftFilterKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_filter_keyboard
            result = get_shift_filter_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_nine_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_filter_keyboard
            result = get_shift_filter_keyboard()
        # 2+2+2+2 filter buttons + 1 back = 9
        assert len(_flat_texts(result)) == 9

    def test_filter_today_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_filter_keyboard
            result = get_shift_filter_keyboard()
        assert "filter_today" in _flat_cbs(result)

    def test_filter_all_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_filter_keyboard
            result = get_shift_filter_keyboard()
        assert "filter_all" in _flat_cbs(result)


# ---------------------------------------------------------------------------
# get_time_tracking_keyboard
# ---------------------------------------------------------------------------

class TestGetTimeTrackingKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_time_tracking_keyboard
            result = get_time_tracking_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_six_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_time_tracking_keyboard
            result = get_time_tracking_keyboard()
        assert len(_flat_texts(result)) == 6

    def test_start_stop_callbacks(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_time_tracking_keyboard
            result = get_time_tracking_keyboard()
        cbs = _flat_cbs(result)
        assert "start_time_tracking" in cbs
        assert "stop_time_tracking" in cbs


# ---------------------------------------------------------------------------
# get_statistics_keyboard
# ---------------------------------------------------------------------------

class TestGetStatisticsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_statistics_keyboard
            result = get_statistics_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_seven_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_statistics_keyboard
            result = get_statistics_keyboard()
        assert len(_flat_texts(result)) == 7


# ---------------------------------------------------------------------------
# get_break_options_keyboard
# ---------------------------------------------------------------------------

class TestGetBreakOptionsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_break_options_keyboard
            result = get_break_options_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_five_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_break_options_keyboard
            result = get_break_options_keyboard()
        assert len(_flat_texts(result)) == 5

    def test_cancel_break_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_break_options_keyboard
            result = get_break_options_keyboard()
        assert "cancel_break" in _flat_cbs(result)


# ---------------------------------------------------------------------------
# get_emergency_keyboard
# ---------------------------------------------------------------------------

class TestGetEmergencyKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_emergency_keyboard
            result = get_emergency_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_six_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_emergency_keyboard
            result = get_emergency_keyboard()
        assert len(_flat_texts(result)) == 6

    def test_cancel_emergency_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_emergency_keyboard
            result = get_emergency_keyboard()
        assert "cancel_emergency" in _flat_cbs(result)


# ---------------------------------------------------------------------------
# get_shift_requests_keyboard
# ---------------------------------------------------------------------------

class TestGetShiftRequestsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_requests_keyboard
            result = get_shift_requests_keyboard(shift_id=10)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_six_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_requests_keyboard
            result = get_shift_requests_keyboard(shift_id=10)
        assert len(_flat_texts(result)) == 6

    def test_callbacks_contain_shift_id(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_requests_keyboard
            result = get_shift_requests_keyboard(shift_id=42)
        cbs = _flat_cbs(result)
        assert any("42" in cb for cb in cbs)


# ---------------------------------------------------------------------------
# get_location_keyboard
# ---------------------------------------------------------------------------

class TestGetLocationKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_location_keyboard
            result = get_location_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_four_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_location_keyboard
            result = get_location_keyboard()
        assert len(_flat_texts(result)) == 4


# ---------------------------------------------------------------------------
# get_shift_completion_keyboard
# ---------------------------------------------------------------------------

class TestGetShiftCompletionKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_completion_keyboard
            result = get_shift_completion_keyboard(shift_id=5)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_four_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_completion_keyboard
            result = get_shift_completion_keyboard(shift_id=5)
        assert len(_flat_texts(result)) == 4

    def test_callbacks_contain_shift_id(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_shift_completion_keyboard
            result = get_shift_completion_keyboard(shift_id=99)
        cbs = _flat_cbs(result)
        assert any("99" in cb for cb in cbs)


# ---------------------------------------------------------------------------
# get_navigation_keyboard
# ---------------------------------------------------------------------------

class TestGetNavigationKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_navigation_keyboard
            result = get_navigation_keyboard(1, 3, "page")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_first_page_has_no_prev(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_navigation_keyboard
            result = get_navigation_keyboard(1, 5, "page")
        cbs = _flat_cbs(result)
        # current_page=1: only page indicator + next button
        assert len(cbs) == 2

    def test_last_page_has_no_next(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_navigation_keyboard
            result = get_navigation_keyboard(5, 5, "page")
        cbs = _flat_cbs(result)
        # prev + page indicator
        assert len(cbs) == 2

    def test_middle_page_has_prev_and_next(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_navigation_keyboard
            result = get_navigation_keyboard(3, 5, "page")
        cbs = _flat_cbs(result)
        assert len(cbs) == 3

    def test_page_indicator_shows_current_and_total(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.my_shifts import get_navigation_keyboard
            result = get_navigation_keyboard(2, 7, "p")
        texts = _flat_texts(result)
        assert "2/7" in texts
