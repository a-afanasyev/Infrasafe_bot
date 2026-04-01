"""
Unit tests for keyboards/request_reports.py

Tests return types and button structure. get_text is mocked.
"""
import pytest
from unittest.mock import patch

from aiogram.types import InlineKeyboardMarkup

GET_TEXT_PATH = "uk_management_bot.keyboards.request_reports.get_text"


def _echo(key: str, language: str = "ru", **kwargs) -> str:
    return key


def _flat_texts(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.text for row in markup.inline_keyboard for btn in row]


def _flat_cbs(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row]


# ---------------------------------------------------------------------------
# get_report_confirmation_keyboard
# ---------------------------------------------------------------------------

class TestGetReportConfirmationKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_reports import get_report_confirmation_keyboard
            result = get_report_confirmation_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_two_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_reports import get_report_confirmation_keyboard
            result = get_report_confirmation_keyboard()
        assert len(_flat_texts(result)) == 2

    def test_confirm_and_cancel_callbacks(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_reports import get_report_confirmation_keyboard
            result = get_report_confirmation_keyboard()
        cbs = _flat_cbs(result)
        assert "confirm_approval" in cbs
        assert "cancel_approval" in cbs

    def test_language_param_forwarded(self):
        with patch(GET_TEXT_PATH, side_effect=_echo) as mock_get_text:
            from uk_management_bot.keyboards.request_reports import get_report_confirmation_keyboard
            get_report_confirmation_keyboard(language="uz")
        calls_languages = [call.kwargs.get("language") for call in mock_get_text.call_args_list]
        assert all(lang == "uz" for lang in calls_languages)


# ---------------------------------------------------------------------------
# get_report_actions_keyboard
# ---------------------------------------------------------------------------

class TestGetReportActionsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_reports import get_report_actions_keyboard
            result = get_report_actions_keyboard("260101-001", "В работе")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_executed_status_has_approve_and_revision_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_reports import get_report_actions_keyboard
            result = get_report_actions_keyboard("260101-001", "Исполнено")
        cbs = _flat_cbs(result)
        assert any(cb.startswith("approve_request_") for cb in cbs)
        assert any(cb.startswith("request_revision_") for cb in cbs)

    def test_approved_status_has_already_approved_button(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_reports import get_report_actions_keyboard
            result = get_report_actions_keyboard("260101-001", "Принято")
        cbs = _flat_cbs(result)
        assert "request_already_approved" in cbs

    def test_common_buttons_always_present(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_reports import get_report_actions_keyboard
            result = get_report_actions_keyboard("260101-001", "В работе")
        cbs = _flat_cbs(result)
        # add_comment, view_comments, back_to_request
        assert any(cb.startswith("add_comment_") for cb in cbs)
        assert any(cb.startswith("view_comments_") for cb in cbs)
        assert any(cb.startswith("view_request_") for cb in cbs)

    def test_callbacks_contain_request_number(self):
        req_num = "260101-007"
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_reports import get_report_actions_keyboard
            result = get_report_actions_keyboard(req_num, "В работе")
        cbs = _flat_cbs(result)
        assert any(req_num in cb for cb in cbs)

    def test_other_status_has_only_common_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_reports import get_report_actions_keyboard
            result = get_report_actions_keyboard("260101-001", "Новая")
        # 3 common buttons only
        assert len(_flat_texts(result)) == 3


# ---------------------------------------------------------------------------
# get_report_details_keyboard
# ---------------------------------------------------------------------------

class TestGetReportDetailsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_reports import get_report_details_keyboard
            result = get_report_details_keyboard(42)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_four_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_reports import get_report_details_keyboard
            result = get_report_details_keyboard(42)
        assert len(_flat_texts(result)) == 4

    def test_callbacks_contain_request_id(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_reports import get_report_details_keyboard
            result = get_report_details_keyboard(99)
        cbs = _flat_cbs(result)
        assert any("99" in cb for cb in cbs)

    def test_full_report_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_reports import get_report_details_keyboard
            result = get_report_details_keyboard(1)
        cbs = _flat_cbs(result)
        assert any(cb.startswith("view_full_report_") for cb in cbs)

    def test_change_history_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_reports import get_report_details_keyboard
            result = get_report_details_keyboard(1)
        cbs = _flat_cbs(result)
        assert any(cb.startswith("view_request_history_") for cb in cbs)

    def test_back_to_report_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.request_reports import get_report_details_keyboard
            result = get_report_details_keyboard(1)
        cbs = _flat_cbs(result)
        assert any(cb.startswith("back_to_report_") for cb in cbs)
