"""
Unit tests for keyboards/shift_management.py

Tests keyboard builders for the shift management module (managers).
ORM objects replaced with MagicMock; get_text is mocked.
"""
import pytest
from unittest.mock import patch, MagicMock
from aiogram.types import InlineKeyboardMarkup
from datetime import date


GET_TEXT_PATH = "uk_management_bot.keyboards.shift_management.get_text"


def _mock_get_text(key: str, language: str = "ru", **kwargs) -> str:
    text = key
    for k, v in kwargs.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def _all_buttons(markup: InlineKeyboardMarkup) -> list:
    return [btn for row in markup.inline_keyboard for btn in row]


def _all_callbacks(markup: InlineKeyboardMarkup) -> list:
    return [btn.callback_data for btn in _all_buttons(markup) if btn.callback_data]


def _make_template(template_id: int, name: str = "Утренняя", start_hour: int = 8,
                   start_minute: int = 0, duration_hours: int = 8,
                   required_specializations: list = None) -> MagicMock:
    t = MagicMock()
    t.id = template_id
    t.name = name
    t.start_hour = start_hour
    t.start_minute = start_minute
    t.duration_hours = duration_hours
    t.required_specializations = required_specializations or []
    return t


def _make_shift(shift_id: int, status: str = "planned") -> MagicMock:
    s = MagicMock()
    s.id = shift_id
    s.status = status
    return s


def _make_executor(telegram_id: int, first_name: str = "Алексей", last_name: str = None) -> MagicMock:
    e = MagicMock()
    e.telegram_id = telegram_id
    e.first_name = first_name
    e.last_name = last_name
    e.specializations = []
    return e


# ---------------------------------------------------------------------------
# get_main_shift_menu
# ---------------------------------------------------------------------------

class TestGetMainShiftMenu:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_main_shift_menu
            result = get_main_shift_menu()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_four_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_main_shift_menu
            result = get_main_shift_menu()
        assert len(_all_buttons(result)) == 4

    def test_callback_data_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_main_shift_menu
            result = get_main_shift_menu()
        cbs = set(_all_callbacks(result))
        assert "shift_planning" in cbs
        assert "shift_analytics" in cbs
        assert "template_management" in cbs
        assert "shift_executor_assignment" in cbs

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_language_accepted(self, language):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_main_shift_menu
            result = get_main_shift_menu(language=language)
        assert isinstance(result, InlineKeyboardMarkup)


# ---------------------------------------------------------------------------
# get_planning_menu
# ---------------------------------------------------------------------------

class TestGetPlanningMenu:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_planning_menu
            result = get_planning_menu()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_five_buttons(self):
        """create_from_template, plan_week, auto_planning, view_schedule, back"""
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_planning_menu
            result = get_planning_menu()
        assert len(_all_buttons(result)) == 5

    def test_back_callback_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_planning_menu
            result = get_planning_menu()
        assert "back_to_shifts" in _all_callbacks(result)


# ---------------------------------------------------------------------------
# get_template_selection_keyboard
# ---------------------------------------------------------------------------

class TestGetTemplateSelectionKeyboard:
    def test_empty_templates_has_back_only(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_template_selection_keyboard
            result = get_template_selection_keyboard(templates=[])
        assert len(_all_buttons(result)) == 1
        assert "back_to_planning" in _all_callbacks(result)

    def test_templates_appear_as_buttons(self):
        templates = [_make_template(i + 1) for i in range(3)]
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_template_selection_keyboard
            result = get_template_selection_keyboard(templates=templates)
        # 3 template buttons + 1 back button
        assert len(_all_buttons(result)) == 4

    def test_template_callback_contains_id(self):
        templates = [_make_template(42)]
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_template_selection_keyboard
            result = get_template_selection_keyboard(templates=templates)
        assert "select_template:42" in _all_callbacks(result)

    def test_single_specialization_shown(self):
        template = _make_template(1, required_specializations=["сантехника"])
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_template_selection_keyboard
            result = get_template_selection_keyboard(templates=[template])
        texts = [btn.text for btn in _all_buttons(result)]
        assert any("сантехника" in t for t in texts)

    def test_multiple_specializations_shows_count(self):
        template = _make_template(1, required_specializations=["сантехника", "электрика"])
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_template_selection_keyboard
            result = get_template_selection_keyboard(templates=[template])
        assert isinstance(result, InlineKeyboardMarkup)


# ---------------------------------------------------------------------------
# get_date_selection_keyboard
# ---------------------------------------------------------------------------

class TestGetDateSelectionKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_date_selection_keyboard
            result = get_date_selection_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_sixteen_buttons(self):
        """15 date buttons + 1 back = 16 total"""
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_date_selection_keyboard
            result = get_date_selection_keyboard()
        assert len(_all_buttons(result)) == 16

    def test_first_callback_is_today(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_date_selection_keyboard
            result = get_date_selection_keyboard()
        cbs = _all_callbacks(result)
        assert cbs[0] == "select_date:0"

    def test_back_callback_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_date_selection_keyboard
            result = get_date_selection_keyboard()
        assert "back_to_planning" in _all_callbacks(result)

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_language_accepted(self, language):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_date_selection_keyboard
            result = get_date_selection_keyboard(language=language)
        assert isinstance(result, InlineKeyboardMarkup)


# ---------------------------------------------------------------------------
# get_analytics_menu
# ---------------------------------------------------------------------------

class TestGetAnalyticsMenu:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_analytics_menu
            result = get_analytics_menu()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_six_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_analytics_menu
            result = get_analytics_menu()
        assert len(_all_buttons(result)) == 6

    def test_back_callback_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_analytics_menu
            result = get_analytics_menu()
        assert "back_to_shifts" in _all_callbacks(result)


# ---------------------------------------------------------------------------
# get_shift_details_keyboard
# ---------------------------------------------------------------------------

class TestGetShiftDetailsKeyboard:
    def test_planned_shift_has_edit_assign_cancel(self):
        shift = _make_shift(1, status="planned")
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_shift_details_keyboard
            result = get_shift_details_keyboard(shift)
        cbs = set(_all_callbacks(result))
        assert "edit_shift:1" in cbs
        assert "assign_executor:1" in cbs
        assert "cancel_shift:1" in cbs

    def test_active_shift_has_requests_contact_end(self):
        shift = _make_shift(2, status="active")
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_shift_details_keyboard
            result = get_shift_details_keyboard(shift)
        cbs = set(_all_callbacks(result))
        assert "view_shift_requests:2" in cbs
        assert "contact_executor:2" in cbs
        assert "end_shift_early:2" in cbs

    def test_completed_shift_has_report_requests_rate(self):
        shift = _make_shift(3, status="completed")
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_shift_details_keyboard
            result = get_shift_details_keyboard(shift)
        cbs = set(_all_callbacks(result))
        assert "shift_report:3" in cbs
        assert "completed_requests:3" in cbs
        assert "rate_executor:3" in cbs

    def test_all_statuses_have_export_and_back(self):
        for status in ["planned", "active", "completed"]:
            shift = _make_shift(10, status=status)
            with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
                from uk_management_bot.keyboards.shift_management import get_shift_details_keyboard
                result = get_shift_details_keyboard(shift)
            cbs = set(_all_callbacks(result))
            assert "export_shift:10" in cbs
            assert "back_to_shifts" in cbs

    def test_unknown_status_has_only_export_and_back(self):
        shift = _make_shift(5, status="cancelled")
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_shift_details_keyboard
            result = get_shift_details_keyboard(shift)
        # Only export + back buttons for unknown status
        assert len(_all_buttons(result)) == 2


# ---------------------------------------------------------------------------
# get_executor_selection_keyboard
# ---------------------------------------------------------------------------

class TestGetExecutorSelectionKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_executor_selection_keyboard
            result = get_executor_selection_keyboard(available_executors=[])
        assert isinstance(result, InlineKeyboardMarkup)

    def test_empty_list_has_auto_and_back(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_executor_selection_keyboard
            result = get_executor_selection_keyboard(available_executors=[])
        cbs = set(_all_callbacks(result))
        assert "auto_assign_executor" in cbs
        assert "back_to_planning" in cbs

    def test_executors_appear_as_buttons(self):
        executors = [_make_executor(i + 100) for i in range(3)]
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_executor_selection_keyboard
            result = get_executor_selection_keyboard(available_executors=executors)
        # 3 executor buttons + auto + back = 5
        assert len(_all_buttons(result)) == 5

    def test_executor_callback_contains_telegram_id(self):
        executor = _make_executor(telegram_id=42)
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_executor_selection_keyboard
            result = get_executor_selection_keyboard(available_executors=[executor])
        assert "assign_to_executor:42" in _all_callbacks(result)

    def test_executor_with_last_name_shown(self):
        executor = _make_executor(42, first_name="Иван", last_name="Иванов")
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_executor_selection_keyboard
            result = get_executor_selection_keyboard(available_executors=[executor])
        texts = [btn.text for btn in _all_buttons(result)]
        assert any("Иванов" in t for t in texts)

    def test_executor_with_specialization(self):
        executor = _make_executor(99)
        executor.specializations = ["сантехника", "электрика"]
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_executor_selection_keyboard
            result = get_executor_selection_keyboard(available_executors=[executor])
        texts = [btn.text for btn in _all_buttons(result)]
        assert any("сантехника" in t for t in texts)


# ---------------------------------------------------------------------------
# get_schedule_view_keyboard
# ---------------------------------------------------------------------------

class TestGetScheduleViewKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_schedule_view_keyboard
            result = get_schedule_view_keyboard(current_date=date.today())
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_seven_buttons(self):
        """prev, next, today, tomorrow, weekly, monthly, back = 7"""
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_schedule_view_keyboard
            result = get_schedule_view_keyboard(current_date=date.today())
        assert len(_all_buttons(result)) == 7

    def test_back_callback_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_schedule_view_keyboard
            result = get_schedule_view_keyboard(current_date=date.today())
        assert "back_to_planning" in _all_callbacks(result)

    def test_schedule_date_callbacks_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_schedule_view_keyboard
            result = get_schedule_view_keyboard(current_date=date(2025, 3, 15))
        cbs = _all_callbacks(result)
        assert any("schedule_date:" in c for c in cbs)


# ---------------------------------------------------------------------------
# get_auto_planning_keyboard
# ---------------------------------------------------------------------------

class TestGetAutoPlanningKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_auto_planning_keyboard
            result = get_auto_planning_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_four_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_auto_planning_keyboard
            result = get_auto_planning_keyboard()
        assert len(_all_buttons(result)) == 4

    def test_callback_data_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_auto_planning_keyboard
            result = get_auto_planning_keyboard()
        cbs = set(_all_callbacks(result))
        assert "auto_plan_week" in cbs
        assert "auto_plan_month" in cbs
        assert "auto_plan_tomorrow" in cbs
        assert "back_to_planning" in cbs


# ---------------------------------------------------------------------------
# get_template_management_keyboard
# ---------------------------------------------------------------------------

class TestGetTemplateManagementKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_template_management_keyboard
            result = get_template_management_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_four_buttons(self):
        # FS-05: убраны 3 мёртвые кнопки (usage_stats/import/export) → 7 стало 4.
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_template_management_keyboard
            result = get_template_management_keyboard()
        assert len(_all_buttons(result)) == 4

    def test_no_dead_callbacks(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_template_management_keyboard
            result = get_template_management_keyboard()
        cbs = set(_all_callbacks(result))
        assert {"template_usage_stats", "import_templates", "export_templates"}.isdisjoint(cbs)

    def test_callback_data_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_template_management_keyboard
            result = get_template_management_keyboard()
        cbs = set(_all_callbacks(result))
        assert "templates_view_all" in cbs
        assert "create_new_template" in cbs
        assert "back_to_shifts" in cbs


# ---------------------------------------------------------------------------
# get_executor_assignment_keyboard
# ---------------------------------------------------------------------------

class TestGetExecutorAssignmentKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_executor_assignment_keyboard
            result = get_executor_assignment_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_seven_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_executor_assignment_keyboard
            result = get_executor_assignment_keyboard()
        assert len(_all_buttons(result)) == 7

    def test_back_callback_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_executor_assignment_keyboard
            result = get_executor_assignment_keyboard()
        assert "back_to_shifts" in _all_callbacks(result)


# ---------------------------------------------------------------------------
# get_confirmation_keyboard
# ---------------------------------------------------------------------------

class TestGetConfirmationKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_confirmation_keyboard
            result = get_confirmation_keyboard("cancel_shift", "42")
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_two_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_confirmation_keyboard
            result = get_confirmation_keyboard("cancel_shift", "42")
        assert len(_all_buttons(result)) == 2

    def test_confirm_callback_contains_action_and_id(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_confirmation_keyboard
            result = get_confirmation_keyboard("cancel_shift", "42")
        cbs = set(_all_callbacks(result))
        assert "confirm_cancel_shift:42" in cbs
        assert "cancel_cancel_shift:42" in cbs

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_language_accepted(self, language):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.shift_management import get_confirmation_keyboard
            result = get_confirmation_keyboard("action", "1", language=language)
        assert isinstance(result, InlineKeyboardMarkup)
