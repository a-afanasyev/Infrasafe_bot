"""
Unit tests for keyboards/request_assignment.py

Tests that each keyboard builder function:
- Returns an InlineKeyboardMarkup
- Contains the expected number of buttons / rows
- Button callback_data values are well-formed strings

No DB, no network. get_text and RequestCallbackHelper are mocked.
"""
import pytest
from unittest.mock import MagicMock, patch
from aiogram.types import InlineKeyboardMarkup


# ---------------------------------------------------------------------------
# Patch targets
# ---------------------------------------------------------------------------

GET_TEXT_PATH = "uk_management_bot.keyboards.request_assignment.get_text"
CALLBACK_HELPER_PATH = "uk_management_bot.keyboards.request_assignment.RequestCallbackHelper"


def _mock_get_text(key: str, language: str = "ru", **kwargs) -> str:
    return key  # echo the key so we can assert on it


def _mock_create_callback(prefix: str, request_number: str) -> str:
    return f"{prefix}{request_number}"


def _all_buttons(markup: InlineKeyboardMarkup) -> list:
    return [btn for row in markup.inline_keyboard for btn in row]


# ---------------------------------------------------------------------------
# get_request_assignment_keyboard
# ---------------------------------------------------------------------------

class TestGetRequestAssignmentKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text), \
             patch(CALLBACK_HELPER_PATH + ".create_callback_data_with_request_number",
                   side_effect=_mock_create_callback):
            from uk_management_bot.keyboards.request_assignment import get_request_assignment_keyboard
            result = get_request_assignment_keyboard("250101-001")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_three_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text), \
             patch(CALLBACK_HELPER_PATH + ".create_callback_data_with_request_number",
                   side_effect=_mock_create_callback):
            from uk_management_bot.keyboards.request_assignment import get_request_assignment_keyboard
            result = get_request_assignment_keyboard("250101-001")
        assert len(_all_buttons(result)) == 3

    def test_cancel_button_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text), \
             patch(CALLBACK_HELPER_PATH + ".create_callback_data_with_request_number",
                   side_effect=_mock_create_callback):
            from uk_management_bot.keyboards.request_assignment import get_request_assignment_keyboard
            result = get_request_assignment_keyboard("250101-001")
        callbacks = [btn.callback_data for btn in _all_buttons(result)]
        assert "cancel_assignment" in callbacks

    def test_buttons_have_non_empty_callback_data(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text), \
             patch(CALLBACK_HELPER_PATH + ".create_callback_data_with_request_number",
                   side_effect=_mock_create_callback):
            from uk_management_bot.keyboards.request_assignment import get_request_assignment_keyboard
            result = get_request_assignment_keyboard("250101-001", language="uz")
        for btn in _all_buttons(result):
            assert btn.callback_data


# ---------------------------------------------------------------------------
# get_specialization_selection_keyboard
# ---------------------------------------------------------------------------

class TestGetSpecializationSelectionKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_specialization_selection_keyboard
            result = get_specialization_selection_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_six_specialization_buttons_plus_cancel(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_specialization_selection_keyboard
            result = get_specialization_selection_keyboard()
        # 6 specializations + 1 cancel = 7 buttons total
        assert len(_all_buttons(result)) == 7

    def test_specialization_callbacks_are_prefixed(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_specialization_selection_keyboard
            result = get_specialization_selection_keyboard()
        spec_buttons = [
            btn for btn in _all_buttons(result)
            if btn.callback_data and btn.callback_data.startswith("specialization_")
        ]
        assert len(spec_buttons) == 6

    def test_rows_have_two_buttons_each(self):
        """Specializations are arranged 2 per row."""
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_specialization_selection_keyboard
            result = get_specialization_selection_keyboard()
        # First 3 rows should each have 2 buttons
        for row in result.inline_keyboard[:3]:
            assert len(row) == 2


# ---------------------------------------------------------------------------
# get_executor_selection_keyboard
# ---------------------------------------------------------------------------

class TestGetExecutorSelectionKeyboard:
    def _make_executors(self, count: int) -> list:
        executors = []
        for i in range(count):
            e = MagicMock()
            e.full_name = f"Executor {i}"
            e.id = i + 1
            executors.append(e)
        return executors

    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_executor_selection_keyboard
            result = get_executor_selection_keyboard([])
        assert isinstance(result, InlineKeyboardMarkup)

    def test_empty_list_has_only_cancel_button(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_executor_selection_keyboard
            result = get_executor_selection_keyboard([])
        buttons = _all_buttons(result)
        assert len(buttons) == 1
        assert buttons[0].callback_data == "cancel_assignment"

    def test_one_executor_has_two_buttons(self):
        executors = self._make_executors(1)
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_executor_selection_keyboard
            result = get_executor_selection_keyboard(executors)
        # 1 executor + cancel
        assert len(_all_buttons(result)) == 2

    def test_executor_callbacks_contain_id(self):
        executors = self._make_executors(3)
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_executor_selection_keyboard
            result = get_executor_selection_keyboard(executors)
        exec_callbacks = [
            btn.callback_data for btn in _all_buttons(result)
            if btn.callback_data and btn.callback_data.startswith("executor_")
        ]
        assert len(exec_callbacks) == 3


# ---------------------------------------------------------------------------
# get_assignment_confirmation_keyboard
# ---------------------------------------------------------------------------

class TestGetAssignmentConfirmationKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_assignment_confirmation_keyboard
            result = get_assignment_confirmation_keyboard("group")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_two_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_assignment_confirmation_keyboard
            result = get_assignment_confirmation_keyboard("individual")
        assert len(_all_buttons(result)) == 2

    def test_confirm_and_cancel_callbacks(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_assignment_confirmation_keyboard
            result = get_assignment_confirmation_keyboard("group")
        callbacks = {btn.callback_data for btn in _all_buttons(result)}
        assert "confirm_assignment" in callbacks
        assert "cancel_assignment" in callbacks


# ---------------------------------------------------------------------------
# get_request_actions_keyboard
# ---------------------------------------------------------------------------

class TestGetRequestActionsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_request_actions_keyboard
            result = get_request_actions_keyboard("250101-010")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_four_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_request_actions_keyboard
            result = get_request_actions_keyboard("250101-010")
        assert len(_all_buttons(result)) == 4

    def test_callbacks_contain_request_number(self):
        rn = "250101-010"
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_request_actions_keyboard
            result = get_request_actions_keyboard(rn)
        for btn in _all_buttons(result):
            assert rn in btn.callback_data


# ---------------------------------------------------------------------------
# get_executor_requests_keyboard
# ---------------------------------------------------------------------------

class TestGetExecutorRequestsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_executor_requests_keyboard
            result = get_executor_requests_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_three_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_executor_requests_keyboard
            result = get_executor_requests_keyboard()
        assert len(_all_buttons(result)) == 3


# ---------------------------------------------------------------------------
# get_request_executor_actions_keyboard
# ---------------------------------------------------------------------------

class TestGetRequestExecutorActionsKeyboard:
    def test_in_progress_status_has_extra_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_request_executor_actions_keyboard
            result = get_request_executor_actions_keyboard(1, "В работе")
        buttons = _all_buttons(result)
        # 3 status-specific + 3 common = 6 total
        assert len(buttons) == 6

    def test_purchase_status_has_return_to_work_button(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_request_executor_actions_keyboard
            result = get_request_executor_actions_keyboard(2, "Закуп")
        callbacks = [btn.callback_data for btn in _all_buttons(result)]
        assert any("return_to_work_" in c for c in callbacks)

    def test_other_status_has_only_common_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_request_executor_actions_keyboard
            result = get_request_executor_actions_keyboard(3, "Новая")
        buttons = _all_buttons(result)
        # Only 3 common buttons (add_comment, view_comments, back_to_requests)
        assert len(buttons) == 3

    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.request_assignment import get_request_executor_actions_keyboard
            result = get_request_executor_actions_keyboard(4, "Новая", language="uz")
        assert isinstance(result, InlineKeyboardMarkup)
