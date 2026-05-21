"""
BUG-BOT-011: `❌ Отмена` mislabeled as Back.

`employee_management.get_cancel_keyboard` callback = `employee_mgmt_main`
(чистая навигация без state-clear) — должен называться "🔙 Назад".

`❌ Отмена` остаётся только для FSM-flow с очисткой состояния
(role_cancel, spec_cancel — у них есть state-filter в handler).
"""
import pytest

from uk_management_bot.keyboards.employee_management import (
    get_cancel_keyboard as employee_get_cancel_keyboard,
    get_roles_management_keyboard,
    get_specializations_selection_keyboard,
)


def _first_button(markup):
    return markup.inline_keyboard[0][0]


class TestBugBot011BackVsCancel:
    @pytest.mark.parametrize("language,expected_emoji,not_emoji", [
        ("ru", "🔙", "❌"),
        ("uz", "🔙", "❌"),
    ])
    def test_employee_navigation_keyboard_uses_back_label(self, language, expected_emoji, not_emoji):
        kb = employee_get_cancel_keyboard(language=language)
        btn = _first_button(kb)
        assert btn.callback_data == "employee_mgmt_main"
        assert expected_emoji in btn.text, (
            f"Кнопка-навигация должна иметь {expected_emoji}, текст='{btn.text}'"
        )
        assert not_emoji not in btn.text, (
            f"Навигационная кнопка не должна содержать {not_emoji} (Отмена), "
            f"текст='{btn.text}'"
        )

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_role_selection_keeps_cancel_for_fsm_flow(self, language):
        """role_cancel — FSM exit, должен оставаться "❌ Отмена"."""
        kb = get_roles_management_keyboard(selected_roles=[], language=language)
        # Последняя строка — кнопки save + cancel
        last_row = kb.inline_keyboard[-1]
        cancel_btn = next(b for b in last_row if b.callback_data == "role_cancel")
        assert "❌" in cancel_btn.text, (
            f"role_cancel (FSM exit) должен сохранить ❌, текст='{cancel_btn.text}'"
        )

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_spec_selection_keeps_cancel_for_fsm_flow(self, language):
        """spec_cancel — FSM exit, должен оставаться "❌ Отмена"."""
        kb = get_specializations_selection_keyboard(selected_specializations=[], language=language)
        last_row = kb.inline_keyboard[-1]
        cancel_btn = next(b for b in last_row if b.callback_data == "spec_cancel")
        assert "❌" in cancel_btn.text, (
            f"spec_cancel (FSM exit) должен сохранить ❌, текст='{cancel_btn.text}'"
        )
