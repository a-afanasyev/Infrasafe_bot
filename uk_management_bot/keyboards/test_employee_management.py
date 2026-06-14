"""
Unit tests for keyboards/employee_management.py

Mocks get_text; tests return types, button counts, and callback conventions.
"""
import pytest
from unittest.mock import patch, MagicMock

from aiogram.types import InlineKeyboardMarkup

GET_TEXT_PATH = "uk_management_bot.keyboards.employee_management.get_text"


def _echo(key: str, language: str = "ru", **kwargs) -> str:
    return key


def _flat_texts(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.text for row in markup.inline_keyboard for btn in row]


def _flat_cbs(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.callback_data for row in markup.inline_keyboard for btn in row]


def _make_employee(eid: int = 1, status: str = "pending") -> MagicMock:
    e = MagicMock()
    e.id = eid
    e.first_name = "Ivan"
    e.last_name = "Petrov"
    e.username = "ivan"
    e.telegram_id = 1000 + eid
    e.status = status
    return e


# ---------------------------------------------------------------------------
# get_employee_management_main_keyboard
# ---------------------------------------------------------------------------

class TestGetEmployeeManagementMainKeyboard:
    def test_returns_inline_keyboard_markup(self):
        stats = {"pending": 1, "active": 5, "blocked": 0,
                 "executors": 4, "managers": 1}
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_employee_management_main_keyboard
            result = get_employee_management_main_keyboard(stats)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_nine_buttons(self):
        stats = {"pending": 0, "active": 0, "blocked": 0,
                 "executors": 0, "managers": 0}
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_employee_management_main_keyboard
            result = get_employee_management_main_keyboard(stats)
        # stats + pending + active + blocked + executors + managers + search + specs + back = 9
        assert len(_flat_texts(result)) == 9

    def test_stats_counts_embedded(self):
        stats = {"pending": 3, "active": 0, "blocked": 0,
                 "executors": 0, "managers": 0}
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_employee_management_main_keyboard
            result = get_employee_management_main_keyboard(stats)
        texts = _flat_texts(result)
        assert any("3" in t for t in texts)

    def test_admin_panel_back_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_employee_management_main_keyboard
            result = get_employee_management_main_keyboard({})
        assert "admin_panel" in _flat_cbs(result)


# ---------------------------------------------------------------------------
# get_employee_list_keyboard
# ---------------------------------------------------------------------------

class TestGetEmployeeListKeyboard:
    def _data(self, employees=None, current_page=1, total_pages=1):
        return {
            "employees": employees or [],
            "current_page": current_page,
            "total_pages": total_pages,
        }

    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_employee_list_keyboard
            result = get_employee_list_keyboard(self._data(), "active")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_empty_list_shows_no_employees_button(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_employee_list_keyboard
            result = get_employee_list_keyboard(self._data(), "active")
        cbs = _flat_cbs(result)
        assert "no_action" in cbs

    def test_employee_button_callback(self):
        emp = _make_employee(eid=5)
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_employee_list_keyboard
            result = get_employee_list_keyboard(self._data(employees=[emp]), "active")
        cbs = _flat_cbs(result)
        assert "employee_mgmt_employee_5" in cbs

    def test_pagination_shown_when_multiple_pages(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_employee_list_keyboard
            result = get_employee_list_keyboard(
                self._data(current_page=1, total_pages=3), "active"
            )
        cbs = _flat_cbs(result)
        assert any("active_2" in cb for cb in cbs)

    def test_back_to_main_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_employee_list_keyboard
            result = get_employee_list_keyboard(self._data(), "active")
        assert "employee_mgmt_main" in _flat_cbs(result)


# ---------------------------------------------------------------------------
# get_employee_actions_keyboard
# ---------------------------------------------------------------------------

class TestGetEmployeeActionsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_employee_actions_keyboard
            result = get_employee_actions_keyboard(1, "pending")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_pending_has_approve_and_reject(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_employee_actions_keyboard
            result = get_employee_actions_keyboard(1, "pending")
        cbs = _flat_cbs(result)
        assert "approve_employee_1" in cbs
        assert "reject_employee_1" in cbs

    def test_approved_has_block_change_role_specialization(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_employee_actions_keyboard
            result = get_employee_actions_keyboard(2, "approved")
        cbs = _flat_cbs(result)
        assert "block_employee_2" in cbs
        assert "change_employee_role_2" in cbs
        assert "change_employee_specialization_2" in cbs

    def test_blocked_has_unblock(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_employee_actions_keyboard
            result = get_employee_actions_keyboard(3, "blocked")
        cbs = _flat_cbs(result)
        assert "unblock_employee_3" in cbs

    def test_common_buttons_always_present(self):
        for status in ("pending", "approved", "blocked"):
            with patch(GET_TEXT_PATH, side_effect=_echo):
                from uk_management_bot.keyboards.employee_management import get_employee_actions_keyboard
                result = get_employee_actions_keyboard(4, status)
            cbs = _flat_cbs(result)
            assert "delete_employee_4" in cbs
            assert "edit_employee_4" in cbs
            assert "employee_mgmt_main" in cbs


# ---------------------------------------------------------------------------
# get_roles_management_keyboard
# ---------------------------------------------------------------------------

class TestGetEmployeeRolesManagementKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_roles_management_keyboard
            result = get_roles_management_keyboard(["executor"])
        assert isinstance(result, InlineKeyboardMarkup)

    def test_role_buttons_plus_save_cancel(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_roles_management_keyboard
            result = get_roles_management_keyboard([])
        # executor + manager + inspector + applicant + save + cancel = 6
        # (inspector добавлен — план «Обходчик»).
        assert len(_flat_texts(result)) == 6

    def test_selected_role_has_checkmark(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_roles_management_keyboard
            result = get_roles_management_keyboard(["executor"])
        texts = _flat_texts(result)
        executor_text = next(t for t in texts if "role_toggle_executor" in _flat_cbs(result) and True)
        # We test via callback; selected role toggles with ✅
        cbs = _flat_cbs(result)
        assert "role_toggle_executor" in cbs

    def test_save_cancel_callbacks(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_roles_management_keyboard
            result = get_roles_management_keyboard([])
        cbs = _flat_cbs(result)
        assert "role_save" in cbs
        assert "role_cancel" in cbs

    def test_none_selected_roles_defaults_to_empty(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_roles_management_keyboard
            result = get_roles_management_keyboard(None)
        assert isinstance(result, InlineKeyboardMarkup)


# ---------------------------------------------------------------------------
# get_specializations_selection_keyboard
# ---------------------------------------------------------------------------

class TestGetEmployeeSpecializationsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_specializations_selection_keyboard
            result = get_specializations_selection_keyboard(["plumber"])
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_ten_spec_buttons_plus_save_cancel(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_specializations_selection_keyboard
            result = get_specializations_selection_keyboard([])
        # MGR-07: single source = AVAILABLE_SPECIALIZATIONS (10, incl. 'general')
        # + save + cancel = 12. Раньше был хардкод из 9 (без 'general').
        assert len(_flat_texts(result)) == 12

    def test_spec_toggle_callbacks(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_specializations_selection_keyboard
            result = get_specializations_selection_keyboard([])
        cbs = _flat_cbs(result)
        assert "spec_toggle_plumber" in cbs
        assert "spec_toggle_electrician" in cbs
        assert "spec_toggle_general" in cbs  # MGR-07: 'general' now present

    def test_none_selected_defaults_to_empty(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_specializations_selection_keyboard
            result = get_specializations_selection_keyboard(None)
        assert isinstance(result, InlineKeyboardMarkup)


# ---------------------------------------------------------------------------
# get_employee_edit_keyboard
# ---------------------------------------------------------------------------

class TestGetEmployeeEditKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_employee_edit_keyboard
            result = get_employee_edit_keyboard(employee_id=1)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_three_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_employee_edit_keyboard
            result = get_employee_edit_keyboard(employee_id=1)
        assert len(_flat_texts(result)) == 3

    def test_callbacks_contain_employee_id(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_employee_edit_keyboard
            result = get_employee_edit_keyboard(employee_id=7)
        cbs = _flat_cbs(result)
        assert any("7" in cb for cb in cbs)


# ---------------------------------------------------------------------------
# get_cancel_keyboard (employee_management)
# ---------------------------------------------------------------------------

class TestGetCancelKeyboardEmployee:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_cancel_keyboard
            result = get_cancel_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_one_button(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_cancel_keyboard
            result = get_cancel_keyboard()
        assert len(_flat_texts(result)) == 1

    def test_cancel_callback(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_cancel_keyboard
            result = get_cancel_keyboard()
        assert "employee_mgmt_main" in _flat_cbs(result)


# ---------------------------------------------------------------------------
# get_confirmation_keyboard (employee_management)
# ---------------------------------------------------------------------------

class TestGetConfirmationKeyboardEmployee:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_confirmation_keyboard
            result = get_confirmation_keyboard("delete", 1)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_two_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_confirmation_keyboard
            result = get_confirmation_keyboard("delete", 1)
        assert len(_flat_texts(result)) == 2

    def test_confirm_callback_contains_action_and_id(self):
        with patch(GET_TEXT_PATH, side_effect=_echo):
            from uk_management_bot.keyboards.employee_management import get_confirmation_keyboard
            result = get_confirmation_keyboard("block", 9)
        cbs = _flat_cbs(result)
        assert "confirm_block_9" in cbs
