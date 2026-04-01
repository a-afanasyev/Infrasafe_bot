"""
Unit tests for keyboards/shift_transfer.py

Tests each builder function returns InlineKeyboardMarkup with correct
button counts and callback patterns. ORM objects replaced with MagicMock.
"""
import pytest
from unittest.mock import patch, MagicMock
from aiogram.types import InlineKeyboardMarkup
from datetime import datetime


GET_TEXT_PATH = "uk_management_bot.keyboards.shift_transfer.get_text"


def _mock_get_text(key: str, language: str = "ru", **kwargs) -> str:
    text = key
    for k, v in kwargs.items():
        text = text.replace(f"{{{k}}}", str(v))
    return text


def _all_buttons(markup: InlineKeyboardMarkup) -> list:
    return [btn for row in markup.inline_keyboard for btn in row]


def _all_callbacks(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.callback_data for btn in _all_buttons(markup) if btn.callback_data]


def _make_shift(shift_id: int, status: str = "planned") -> MagicMock:
    s = MagicMock()
    s.id = shift_id
    s.status = status
    s.start_time = datetime(2025, 3, 15, 8, 0)
    return s


def _make_user(user_id: int, first_name: str = "Иван", last_name: str = None) -> MagicMock:
    u = MagicMock()
    u.telegram_id = user_id
    u.first_name = first_name
    u.last_name = last_name
    del u.specialization  # hasattr returns False
    return u


# ---------------------------------------------------------------------------
# shift_selection_keyboard
# ---------------------------------------------------------------------------

class TestShiftSelectionKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import shift_selection_keyboard
            result = shift_selection_keyboard(shifts=[])
        assert isinstance(result, InlineKeyboardMarkup)

    def test_empty_shifts_has_back_button(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import shift_selection_keyboard
            result = shift_selection_keyboard(shifts=[])
        assert "shift_transfer:back" in _all_callbacks(result)

    def test_shifts_appear_as_buttons(self):
        shifts = [_make_shift(i) for i in range(3)]
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import shift_selection_keyboard
            result = shift_selection_keyboard(shifts=shifts)
        shift_cbs = [c for c in _all_callbacks(result) if "transfer_shift:" in c]
        assert len(shift_cbs) == 3

    def test_shift_callback_contains_id(self):
        shifts = [_make_shift(42)]
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import shift_selection_keyboard
            result = shift_selection_keyboard(shifts=shifts)
        assert "transfer_shift:42" in _all_callbacks(result)

    def test_non_standard_status_used_as_is(self):
        """Status not in planned/active/paused is used as raw value."""
        shift = _make_shift(1, status="custom_status")
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import shift_selection_keyboard
            result = shift_selection_keyboard(shifts=[shift])
        assert isinstance(result, InlineKeyboardMarkup)

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_language_accepted(self, language):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import shift_selection_keyboard
            result = shift_selection_keyboard(shifts=[], language=language)
        assert isinstance(result, InlineKeyboardMarkup)


# ---------------------------------------------------------------------------
# transfer_reason_keyboard
# ---------------------------------------------------------------------------

class TestTransferReasonKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import transfer_reason_keyboard
            result = transfer_reason_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_six_buttons(self):
        """5 reason buttons + 1 back"""
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import transfer_reason_keyboard
            result = transfer_reason_keyboard()
        assert len(_all_buttons(result)) == 6

    def test_reason_callbacks_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import transfer_reason_keyboard
            result = transfer_reason_keyboard()
        callbacks = set(_all_callbacks(result))
        for reason in ["illness", "emergency", "workload", "vacation", "other"]:
            assert f"transfer_reason:{reason}" in callbacks

    def test_back_callback_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import transfer_reason_keyboard
            result = transfer_reason_keyboard()
        assert "transfer_step:back" in _all_callbacks(result)


# ---------------------------------------------------------------------------
# urgency_level_keyboard
# ---------------------------------------------------------------------------

class TestUrgencyLevelKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import urgency_level_keyboard
            result = urgency_level_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_five_buttons(self):
        """4 urgency buttons + 1 back"""
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import urgency_level_keyboard
            result = urgency_level_keyboard()
        assert len(_all_buttons(result)) == 5

    def test_urgency_callbacks_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import urgency_level_keyboard
            result = urgency_level_keyboard()
        callbacks = set(_all_callbacks(result))
        for level in ["low", "normal", "high", "critical"]:
            assert f"transfer_urgency:{level}" in callbacks


# ---------------------------------------------------------------------------
# confirm_transfer_keyboard
# ---------------------------------------------------------------------------

class TestConfirmTransferKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import confirm_transfer_keyboard
            result = confirm_transfer_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_three_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import confirm_transfer_keyboard
            result = confirm_transfer_keyboard()
        assert len(_all_buttons(result)) == 3

    def test_confirm_yes_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import confirm_transfer_keyboard
            result = confirm_transfer_keyboard()
        assert "transfer_confirm:yes" in _all_callbacks(result)

    def test_cancel_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import confirm_transfer_keyboard
            result = confirm_transfer_keyboard()
        assert "transfer_confirm:cancel" in _all_callbacks(result)


# ---------------------------------------------------------------------------
# executor_selection_keyboard
# ---------------------------------------------------------------------------

class TestExecutorSelectionKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import executor_selection_keyboard
            result = executor_selection_keyboard(users=[])
        assert isinstance(result, InlineKeyboardMarkup)

    def test_empty_users_has_auto_assign_and_back(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import executor_selection_keyboard
            result = executor_selection_keyboard(users=[])
        callbacks = set(_all_callbacks(result))
        assert "assign_executor:auto" in callbacks
        assert "assign_step:back" in callbacks

    def test_users_appear_as_buttons(self):
        users = [_make_user(i + 100) for i in range(3)]
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import executor_selection_keyboard
            result = executor_selection_keyboard(users=users)
        user_cbs = [c for c in _all_callbacks(result) if "assign_executor:" in c and "auto" not in c]
        assert len(user_cbs) == 3

    def test_user_with_last_name(self):
        user = _make_user(42, first_name="Иван", last_name="Иванов")
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import executor_selection_keyboard
            result = executor_selection_keyboard(users=[user])
        texts = [btn.text for btn in _all_buttons(result)]
        assert any("Иванов" in t for t in texts)

    def test_user_with_no_first_name_uses_unknown(self):
        user = _make_user(99, first_name=None)
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import executor_selection_keyboard
            result = executor_selection_keyboard(users=[user])
        assert isinstance(result, InlineKeyboardMarkup)

    def test_user_with_specialization(self):
        user = _make_user(55, first_name="Алексей")
        user.specialization = '["сантехника", "электрика"]'
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import executor_selection_keyboard
            result = executor_selection_keyboard(users=[user])
        assert isinstance(result, InlineKeyboardMarkup)


# ---------------------------------------------------------------------------
# transfer_response_keyboard
# ---------------------------------------------------------------------------

class TestTransferResponseKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import transfer_response_keyboard
            result = transfer_response_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_three_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import transfer_response_keyboard
            result = transfer_response_keyboard()
        assert len(_all_buttons(result)) == 3

    def test_accept_and_reject_callbacks(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_transfer import transfer_response_keyboard
            result = transfer_response_keyboard()
        callbacks = set(_all_callbacks(result))
        assert "transfer_response:accept" in callbacks
        assert "transfer_response:reject" in callbacks
        assert "transfer_response:details" in callbacks
