"""
BUG-BOT-010: Двойные иконки в кнопках (`◀️ 🔙 Назад`, `💾 💾 Сохранить`, `🔄 🔄 Обновить`).

После фикса builder возвращает кнопку с ровно одной иконкой
для buttons.back / buttons.save / buttons.refresh.
"""
import pytest

from uk_management_bot.keyboards.user_management import (
    get_user_management_main_keyboard,
    get_user_list_keyboard,
    get_roles_management_keyboard,
    get_specializations_selection_keyboard,
    get_search_filters_keyboard,
)
from uk_management_bot.keyboards.employee_management import (
    get_employee_management_main_keyboard,
)
from uk_management_bot.keyboards.user_verification import (
    get_verification_main_keyboard,
)


def _collect_button_texts(markup) -> list[str]:
    texts = []
    for row in markup.inline_keyboard:
        for btn in row:
            texts.append(btn.text)
    return texts


def _count_back_save_refresh_emoji(text: str) -> int:
    return sum(text.count(e) for e in ("🔙", "◀️", "💾", "🔄")) - text.count("🔄 Сбросить") - text.count("🔄 Filtrlarni")


class TestBugBot010NoDoubleIcons:
    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_user_mgmt_main_keyboard_back_button_single_icon(self, language):
        kb = get_user_management_main_keyboard(
            stats={"pending": 1, "approved": 2, "blocked": 0, "staff": 3},
            language=language,
        )
        for text in _collect_button_texts(kb):
            if "Назад" in text or "Orqaga" in text:
                # Должна быть ровно одна иконка (🔙 из template), без ◀️
                assert "◀️" not in text, f"Двойная иконка в '{text}'"
                assert text.count("🔙") == 1, f"Должна быть одна 🔙 в '{text}'"

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_user_list_keyboard_refresh_and_back_single_icon(self, language):
        users_data = {"users": [], "page": 1, "total_pages": 1, "has_prev": False, "has_next": False}
        kb = get_user_list_keyboard(users_data, "pending", language=language)
        for text in _collect_button_texts(kb):
            if "Обновить" in text or "Yangilash" in text:
                assert text.count("🔄") == 1, f"Двойной 🔄 в '{text}'"
            if "Назад" in text or "Orqaga" in text:
                assert "◀️" not in text, f"Двойная иконка в '{text}'"

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_roles_management_save_button_single_icon(self, language):
        kb = get_roles_management_keyboard(user_roles=["applicant"], language=language)
        for text in _collect_button_texts(kb):
            if "Сохранить" in text or "Saqlash" in text:
                assert text.count("💾") == 1, f"Двойной 💾 в '{text}'"

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_specializations_keyboard_save_button_single_icon(self, language):
        kb = get_specializations_selection_keyboard(user_specializations=[], language=language)
        for text in _collect_button_texts(kb):
            if "Сохранить" in text or "Saqlash" in text:
                assert text.count("💾") == 1, f"Двойной 💾 в '{text}'"

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_search_filters_back_button_single_icon(self, language):
        kb = get_search_filters_keyboard(language=language)
        for text in _collect_button_texts(kb):
            if "Назад" in text or "Orqaga" in text:
                assert "◀️" not in text, f"Двойная иконка в '{text}'"

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_employee_management_main_back_single_icon(self, language):
        kb = get_employee_management_main_keyboard(
            stats={"pending": 0, "active": 0, "blocked": 0, "executors": 0, "managers": 0},
            language=language,
        )
        for text in _collect_button_texts(kb):
            if "Назад" in text or "Orqaga" in text:
                assert "◀️" not in text, f"Двойная иконка в '{text}'"

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_verification_main_back_single_icon(self, language):
        kb = get_verification_main_keyboard(
            stats={"pending": 0, "verified": 0, "rejected": 0},
            language=language,
        )
        for text in _collect_button_texts(kb):
            if "Назад" in text or "Orqaga" in text:
                assert "◀️" not in text, f"Двойная иконка в '{text}'"
