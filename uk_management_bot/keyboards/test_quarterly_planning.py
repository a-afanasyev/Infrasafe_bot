"""
Unit tests for keyboards/quarterly_planning.py

Tests that each builder function returns InlineKeyboardMarkup with
correct button counts and callback_data patterns.
No DB, no network — get_text is mocked.
"""
import sys
import pytest
from unittest.mock import patch, MagicMock
from aiogram.types import InlineKeyboardMarkup

# Patch the missing SPECIALIZATION_CONFIGS before any import of quarterly_planning
_mock_spec_configs = {
    "сантехника": MagicMock(schedule_type=MagicMock(value="workday_5_2")),
    "электрика": MagicMock(schedule_type=MagicMock(value="workday_5_2")),
    "слесарные_работы": MagicMock(schedule_type=MagicMock(value="shift_2_2")),
    "мелкий_ремонт": MagicMock(schedule_type=MagicMock(value="flexible")),
    "уборка": MagicMock(schedule_type=MagicMock(value="duty_24_3")),
    "вывоз_мусора": MagicMock(schedule_type=MagicMock(value="workday_5_2")),
    "дезинфекция": MagicMock(schedule_type=MagicMock(value="flexible")),
    "озеленение": MagicMock(schedule_type=MagicMock(value="workday_5_2")),
    "охрана": MagicMock(schedule_type=MagicMock(value="duty_24_3")),
    "видеонаблюдение": MagicMock(schedule_type=MagicMock(value="workday_5_2")),
    "контроль_доступа": MagicMock(schedule_type=MagicMock(value="shift_2_2")),
    "управляющий": MagicMock(schedule_type=MagicMock(value="flexible")),
}

# Inject mock into sys.modules so quarterly_planning can import it
_spec_mod = MagicMock()
_spec_mod.SPECIALIZATION_CONFIGS = _mock_spec_configs
sys.modules.setdefault(
    "uk_management_bot.services.specialization_planning_service",
    _spec_mod
)

GET_TEXT_PATH = "uk_management_bot.keyboards.quarterly_planning.get_text"


def _mock_get_text(key: str, language: str = "ru", **kwargs) -> str:
    # Return key itself, applying format kwargs when needed
    text = key
    for k, v in kwargs.items():
        text = text.replace(f"{{{k}}}", str(v))
    return text


def _all_inline_buttons(markup: InlineKeyboardMarkup) -> list:
    return [btn for row in markup.inline_keyboard for btn in row]


def _all_callbacks(markup: InlineKeyboardMarkup) -> list[str]:
    return [btn.callback_data for btn in _all_inline_buttons(markup) if btn.callback_data]


# ---------------------------------------------------------------------------
# get_quarterly_planning_menu
# ---------------------------------------------------------------------------

class TestGetQuarterlyPlanningMenu:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_quarterly_planning_menu
            result = get_quarterly_planning_menu()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_five_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_quarterly_planning_menu
            result = get_quarterly_planning_menu()
        assert len(_all_inline_buttons(result)) == 5

    def test_back_callback_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_quarterly_planning_menu
            result = get_quarterly_planning_menu()
        assert "back_to_main" in _all_callbacks(result)

    def test_main_action_callbacks_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_quarterly_planning_menu
            result = get_quarterly_planning_menu()
        callbacks = set(_all_callbacks(result))
        assert "qp_create_plan" in callbacks
        assert "qp_current_plans" in callbacks
        assert "qp_statistics" in callbacks

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_language_accepted(self, language):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_quarterly_planning_menu
            result = get_quarterly_planning_menu(language=language)
        assert isinstance(result, InlineKeyboardMarkup)


# ---------------------------------------------------------------------------
# get_quarter_selection_keyboard
# ---------------------------------------------------------------------------

class TestGetQuarterSelectionKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_quarter_selection_keyboard
            result = get_quarter_selection_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_six_buttons(self):
        """4 quarters + 1 next year + 1 back"""
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_quarter_selection_keyboard
            result = get_quarter_selection_keyboard()
        assert len(_all_inline_buttons(result)) == 6

    def test_quarter_callbacks_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_quarter_selection_keyboard
            result = get_quarter_selection_keyboard()
        callbacks = _all_callbacks(result)
        quarter_cbs = [c for c in callbacks if c.startswith("qp_quarter_")]
        assert len(quarter_cbs) == 4

    def test_back_callback_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_quarter_selection_keyboard
            result = get_quarter_selection_keyboard()
        assert "qp_main_menu" in _all_callbacks(result)


# ---------------------------------------------------------------------------
# get_year_quarters_keyboard
# ---------------------------------------------------------------------------

class TestGetYearQuartersKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_year_quarters_keyboard
            result = get_year_quarters_keyboard(year=2026)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_five_buttons(self):
        """4 quarter buttons + 1 back button"""
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_year_quarters_keyboard
            result = get_year_quarters_keyboard(year=2026)
        assert len(_all_inline_buttons(result)) == 5

    def test_callbacks_contain_year(self):
        year = 2027
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_year_quarters_keyboard
            result = get_year_quarters_keyboard(year=year)
        quarter_cbs = [c for c in _all_callbacks(result) if "qp_quarter_" in c]
        for cb in quarter_cbs:
            assert str(year) in cb


# ---------------------------------------------------------------------------
# get_specialization_selection_keyboard
# ---------------------------------------------------------------------------

class TestGetSpecializationSelectionKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_specialization_selection_keyboard
            result = get_specialization_selection_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_no_selected_has_select_all_button(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_specialization_selection_keyboard
            result = get_specialization_selection_keyboard(selected=[])
        callbacks = _all_callbacks(result)
        assert "qp_select_all" in callbacks

    def test_selected_items_shows_continue_button(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_specialization_selection_keyboard
            result = get_specialization_selection_keyboard(selected=["сантехника"])
        callbacks = _all_callbacks(result)
        assert "qp_confirm_specializations" in callbacks

    def test_selected_items_shows_clear_button(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_specialization_selection_keyboard
            result = get_specialization_selection_keyboard(selected=["уборка"])
        callbacks = _all_callbacks(result)
        assert "qp_clear_selection" in callbacks

    def test_none_selected_defaults_to_empty(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_specialization_selection_keyboard
            result = get_specialization_selection_keyboard(selected=None)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_toggle_callbacks_use_spec_name(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_specialization_selection_keyboard
            result = get_specialization_selection_keyboard()
        toggle_cbs = [c for c in _all_callbacks(result) if c.startswith("qp_toggle_spec_")]
        assert len(toggle_cbs) > 0


# ---------------------------------------------------------------------------
# get_planning_confirmation_keyboard
# ---------------------------------------------------------------------------

class TestGetPlanningConfirmationKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_planning_confirmation_keyboard
            result = get_planning_confirmation_keyboard(year=2026, quarter=1, specializations=["уборка"])
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_eight_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_planning_confirmation_keyboard
            result = get_planning_confirmation_keyboard(year=2026, quarter=2, specializations=[])
        assert len(_all_inline_buttons(result)) == 8

    def test_execute_callback_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_planning_confirmation_keyboard
            result = get_planning_confirmation_keyboard(year=2026, quarter=3, specializations=[])
        assert "qp_execute_planning" in _all_callbacks(result)

    @pytest.mark.parametrize("quarter", [1, 2, 3, 4])
    def test_all_quarters_accepted(self, quarter):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_planning_confirmation_keyboard
            result = get_planning_confirmation_keyboard(year=2026, quarter=quarter, specializations=[])
        assert isinstance(result, InlineKeyboardMarkup)


# ---------------------------------------------------------------------------
# get_planning_results_keyboard
# ---------------------------------------------------------------------------

class TestGetPlanningResultsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_planning_results_keyboard
            result = get_planning_results_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_without_plan_id_has_three_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_planning_results_keyboard
            result = get_planning_results_keyboard(plan_id=None)
        assert len(_all_inline_buttons(result)) == 3

    def test_with_plan_id_has_more_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_planning_results_keyboard
            result = get_planning_results_keyboard(plan_id=42)
        assert len(_all_inline_buttons(result)) > 3

    def test_with_conflicts_shows_resolve_button(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_planning_results_keyboard
            result = get_planning_results_keyboard(plan_id=10, has_conflicts=True)
        callbacks = _all_callbacks(result)
        assert any("qp_resolve_conflicts_10" in c for c in callbacks)

    def test_without_conflicts_no_resolve_button(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_planning_results_keyboard
            result = get_planning_results_keyboard(plan_id=10, has_conflicts=False)
        callbacks = _all_callbacks(result)
        assert not any("resolve_conflicts" in c for c in callbacks)

    def test_plan_specific_callbacks_contain_plan_id(self):
        plan_id = 99
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_planning_results_keyboard
            result = get_planning_results_keyboard(plan_id=plan_id)
        plan_cbs = [c for c in _all_callbacks(result) if str(plan_id) in c]
        assert len(plan_cbs) > 0


# ---------------------------------------------------------------------------
# get_transfer_management_keyboard
# ---------------------------------------------------------------------------

class TestGetTransferManagementKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_transfer_management_keyboard
            result = get_transfer_management_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_six_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_transfer_management_keyboard
            result = get_transfer_management_keyboard()
        assert len(_all_inline_buttons(result)) == 6

    def test_back_to_main_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_transfer_management_keyboard
            result = get_transfer_management_keyboard()
        assert "qp_main_menu" in _all_callbacks(result)


# ---------------------------------------------------------------------------
# get_statistics_keyboard
# ---------------------------------------------------------------------------

class TestGetStatisticsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_statistics_keyboard
            result = get_statistics_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_seven_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_statistics_keyboard
            result = get_statistics_keyboard()
        assert len(_all_inline_buttons(result)) == 7

    def test_stats_callbacks_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_statistics_keyboard
            result = get_statistics_keyboard()
        callbacks = set(_all_callbacks(result))
        assert "qp_stats_efficiency" in callbacks
        assert "qp_stats_workload" in callbacks


# ---------------------------------------------------------------------------
# get_advanced_settings_keyboard
# ---------------------------------------------------------------------------

class TestGetAdvancedSettingsKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_advanced_settings_keyboard
            result = get_advanced_settings_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_default_settings_none(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_advanced_settings_keyboard
            result = get_advanced_settings_keyboard(settings=None)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_coverage_247_false_shows_x_emoji(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_advanced_settings_keyboard
            result = get_advanced_settings_keyboard(settings={"coverage_24_7": False})
        texts = [btn.text for row in result.inline_keyboard for btn in row]
        # First button text should start with ❌ (coverage disabled)
        assert any("❌" in t for t in texts)

    def test_coverage_247_true_shows_check_emoji(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_advanced_settings_keyboard
            result = get_advanced_settings_keyboard(settings={"coverage_24_7": True})
        texts = [btn.text for row in result.inline_keyboard for btn in row]
        assert any("✅" in t for t in texts)

    def test_save_and_reset_callbacks_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_advanced_settings_keyboard
            result = get_advanced_settings_keyboard()
        callbacks = set(_all_callbacks(result))
        assert "qp_save_settings" in callbacks
        assert "qp_reset_settings" in callbacks


# ---------------------------------------------------------------------------
# get_plan_preview_keyboard
# ---------------------------------------------------------------------------

class TestGetPlanPreviewKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_plan_preview_keyboard
            result = get_plan_preview_keyboard()
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_six_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_plan_preview_keyboard
            result = get_plan_preview_keyboard()
        assert len(_all_inline_buttons(result)) == 6

    def test_preview_callbacks_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_plan_preview_keyboard
            result = get_plan_preview_keyboard()
        callbacks = set(_all_callbacks(result))
        assert "qp_preview_calendar" in callbacks
        assert "qp_preview_employees" in callbacks


# ---------------------------------------------------------------------------
# get_conflict_resolution_keyboard
# ---------------------------------------------------------------------------

class TestGetConflictResolutionKeyboard:
    def test_returns_inline_keyboard_markup(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_conflict_resolution_keyboard
            result = get_conflict_resolution_keyboard(conflict_id=1)
        assert isinstance(result, InlineKeyboardMarkup)

    def test_has_six_buttons(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_conflict_resolution_keyboard
            result = get_conflict_resolution_keyboard(conflict_id=5)
        assert len(_all_inline_buttons(result)) == 6

    def test_callbacks_contain_conflict_id(self):
        conflict_id = 42
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_conflict_resolution_keyboard
            result = get_conflict_resolution_keyboard(conflict_id=conflict_id)
        callbacks = _all_callbacks(result)
        id_callbacks = [c for c in callbacks if str(conflict_id) in c]
        assert len(id_callbacks) > 0

    def test_auto_resolve_callback_present(self):
        with patch(GET_TEXT_PATH, side_effect=_mock_get_text):
            from uk_management_bot.keyboards.quarterly_planning import get_conflict_resolution_keyboard
            result = get_conflict_resolution_keyboard(conflict_id=7)
        assert any("qp_auto_resolve_7" in c for c in _all_callbacks(result))
