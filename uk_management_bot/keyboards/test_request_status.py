"""
Unit tests for keyboards/request_status.py

Tests return types and button-count logic for all keyboard builder functions.
get_text and get_status_with_emoji are mocked so tests are locale-independent.
"""
import pytest
from unittest.mock import patch

from aiogram.types import InlineKeyboardMarkup

GET_TEXT_PATH = "uk_management_bot.keyboards.request_status.get_text"
GET_STATUS_PATH = "uk_management_bot.keyboards.request_status.get_status_with_emoji"


def _echo(key: str, language: str = "ru", **kwargs) -> str:
    return key


def _echo_status(status: str, language: str = "ru", **kwargs) -> str:
    return f"status:{status}"


def _flat_texts(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.text for row in markup.inline_keyboard for btn in row]


def _flat_cbs(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row]


# ---------------------------------------------------------------------------
# get_status_selection_keyboard
# ---------------------------------------------------------------------------

class TestGetStatusSelectionKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo), \
             patch(GET_STATUS_PATH, side_effect=_echo_status):
            from uk_management_bot.keyboards.request_status import get_status_selection_keyboard
            result = get_status_selection_keyboard(["В работе", "Исполнено"])
        assert isinstance(result, InlineKeyboardMarkup)

    def test_button_count_equals_statuses_plus_cancel(self):
        statuses = ["В работе", "Уточнение", "Исполнено"]
        with patch(GET_TEXT_PATH, side_effect=_echo), \
             patch(GET_STATUS_PATH, side_effect=_echo_status):
            from uk_management_bot.keyboards.request_status import get_status_selection_keyboard
            result = get_status_selection_keyboard(statuses)
        texts = _flat_texts(result)
        # one button per status + one cancel button
        assert len(texts) == len(statuses) + 1

    def test_cancel_button_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo), \
             patch(GET_STATUS_PATH, side_effect=_echo_status):
            from uk_management_bot.keyboards.request_status import get_status_selection_keyboard
            result = get_status_selection_keyboard(["В работе"])
        cbs = _flat_cbs(result)
        assert "cancel_status_change" in cbs

    def test_status_button_callback_prefix(self):
        statuses = ["В работе"]
        with patch(GET_TEXT_PATH, side_effect=_echo), \
             patch(GET_STATUS_PATH, side_effect=_echo_status):
            from uk_management_bot.keyboards.request_status import get_status_selection_keyboard
            result = get_status_selection_keyboard(statuses)
        cbs = _flat_cbs(result)
        assert any(cb.startswith("status_") for cb in cbs)

    def test_empty_statuses_has_only_cancel(self):
        with patch(GET_TEXT_PATH, side_effect=_echo), \
             patch(GET_STATUS_PATH, side_effect=_echo_status):
            from uk_management_bot.keyboards.request_status import get_status_selection_keyboard
            result = get_status_selection_keyboard([])
        assert len(_flat_texts(result)) == 1


# ---------------------------------------------------------------------------
# get_status_confirmation_keyboard
# ---------------------------------------------------------------------------

class TestGetStatusConfirmationKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_status_confirmation_keyboard
            result = get_status_confirmation_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_exactly_two_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_status_confirmation_keyboard
            result = get_status_confirmation_keyboard()
        assert len(_flat_texts(result)) == 2

    def test_confirm_and_cancel_callbacks(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_status_confirmation_keyboard
            result = get_status_confirmation_keyboard()
        cbs = _flat_cbs(result)
        assert "confirm_status_change" in cbs
        assert "cancel_status_change" in cbs


# ---------------------------------------------------------------------------
# get_executor_status_actions_keyboard
# ---------------------------------------------------------------------------

class TestGetExecutorStatusActionsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_executor_status_actions_keyboard
            result = get_executor_status_actions_keyboard("260101-001", "В работе")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_in_progress_has_three_status_specific_buttons(self):
        """For В работе status, 3 extra action buttons + 3 common = 6 total."""
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_executor_status_actions_keyboard
            result = get_executor_status_actions_keyboard("260101-001", "В работе")
        texts = _flat_texts(result)
        assert len(texts) == 6  # 3 status-specific + add_comment + view_comments + back

    def test_purchase_status_has_return_to_work(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_executor_status_actions_keyboard
            result = get_executor_status_actions_keyboard("260101-001", "Закуп")
        cbs = _flat_cbs(result)
        assert any("return_to_work_" in cb for cb in cbs)

    def test_completed_status_has_view_report(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_executor_status_actions_keyboard
            result = get_executor_status_actions_keyboard("260101-001", "Исполнено")
        cbs = _flat_cbs(result)
        assert any("view_report_" in cb for cb in cbs)

    def test_back_to_requests_always_present(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_executor_status_actions_keyboard
            result = get_executor_status_actions_keyboard("260101-001", "Новая")
        cbs = _flat_cbs(result)
        assert "back_to_requests" in cbs

    def test_other_status_has_three_common_buttons(self):
        """Unknown status: only 3 common buttons."""
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_executor_status_actions_keyboard
            result = get_executor_status_actions_keyboard("260101-001", "Новая")
        assert len(_flat_texts(result)) == 3


# ---------------------------------------------------------------------------
# get_manager_status_actions_keyboard
# ---------------------------------------------------------------------------

class TestGetManagerStatusActionsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_manager_status_actions_keyboard
            result = get_manager_status_actions_keyboard("260101-001", "Новая")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_new_status_has_assign_and_take_to_work(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_manager_status_actions_keyboard
            result = get_manager_status_actions_keyboard("260101-001", "Новая")
        cbs = _flat_cbs(result)
        assert any("assign_request_" in cb for cb in cbs)
        # take to work goes to В работе status
        assert any("В работе" in cb for cb in cbs)

    def test_in_progress_has_clarification_and_complete(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_manager_status_actions_keyboard
            result = get_manager_status_actions_keyboard("260101-001", "В работе")
        cbs = _flat_cbs(result)
        assert any("Уточнение" in cb for cb in cbs)
        assert any("Исполнено" in cb for cb in cbs)

    def test_completed_status_has_accept_work(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_manager_status_actions_keyboard
            result = get_manager_status_actions_keyboard("260101-001", "Исполнено")
        cbs = _flat_cbs(result)
        assert any("Принято" in cb for cb in cbs)

    def test_common_buttons_always_present(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_manager_status_actions_keyboard
            result = get_manager_status_actions_keyboard("260101-001", "Новая")
        cbs = _flat_cbs(result)
        assert any("add_comment_" in cb for cb in cbs)
        assert any("view_comments_" in cb for cb in cbs)
        assert any("view_assignments_" in cb for cb in cbs)
        assert "back_to_requests" in cbs


# ---------------------------------------------------------------------------
# get_applicant_status_actions_keyboard
# ---------------------------------------------------------------------------

class TestGetApplicantStatusActionsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_applicant_status_actions_keyboard
            result = get_applicant_status_actions_keyboard("260101-001", "В работе")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_completed_status_has_accept_work_button(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_applicant_status_actions_keyboard
            result = get_applicant_status_actions_keyboard("260101-001", "Исполнено")
        cbs = _flat_cbs(result)
        assert any("Принято" in cb for cb in cbs)

    def test_non_completed_status_no_accept_button(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_applicant_status_actions_keyboard
            result = get_applicant_status_actions_keyboard("260101-001", "В работе")
        cbs = _flat_cbs(result)
        assert not any("Принято" in cb for cb in cbs)

    def test_always_has_three_common_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_applicant_status_actions_keyboard
            result = get_applicant_status_actions_keyboard("260101-001", "В работе")
        assert len(_flat_texts(result)) == 3  # view_comments, view_report, back

    def test_back_to_requests_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_applicant_status_actions_keyboard
            result = get_applicant_status_actions_keyboard("260101-001", "В работе")
        assert "back_to_requests" in _flat_cbs(result)


# ---------------------------------------------------------------------------
# get_quick_status_actions_keyboard
# ---------------------------------------------------------------------------

class TestGetQuickStatusActionsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_quick_status_actions_keyboard
            result = get_quick_status_actions_keyboard("260101-001")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_six_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_quick_status_actions_keyboard
            result = get_quick_status_actions_keyboard("260101-001")
        # 2 quick status buttons row 1 + 2 quick status buttons row 2 + comment + cancel
        assert len(_flat_texts(result)) == 6

    def test_cancel_button_present(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_quick_status_actions_keyboard
            result = get_quick_status_actions_keyboard("260101-001")
        assert "cancel_status_change" in _flat_cbs(result)

    def test_quick_status_callbacks_contain_request_number(self):
        req_num = "260101-042"
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_status import get_quick_status_actions_keyboard
            result = get_quick_status_actions_keyboard(req_num)
        cbs = _flat_cbs(result)
        quick_cbs = [cb for cb in cbs if cb.startswith("quick_status_")]
        assert len(quick_cbs) == 4
        for cb in quick_cbs:
            assert req_num in cb
