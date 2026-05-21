"""
BUG-BOT-023: Employee detail показывает raw DB values.

После фикса:
- `Статус: approved` → `Статус: ✅ Одобрен`
- `Роль: applicant, executor, manager` → `Роль: Заявитель, Исполнитель, Менеджер`
- `Специализация: ["plumber", "electrician", ...]` → локализованный список через запятую.
"""
import json
import pytest

from uk_management_bot.utils.employee_display import (
    format_user_status,
    format_roles,
    format_specializations,
)


class TestBugBot023EmployeeDisplay:
    @pytest.mark.parametrize("status,language,expected", [
        ("approved", "ru", "✅ Одобрен"),
        ("approved", "uz", "✅ Tasdiqlangan"),
        ("pending", "ru", "⏳ Ожидает одобрения"),
        ("pending", "uz", "⏳ Tasdiqlanishi kutilmoqda"),
        ("blocked", "ru", "🚫 Заблокирован"),
        ("blocked", "uz", "🚫 Bloklangan"),
    ])
    def test_user_status_localized(self, status, language, expected):
        assert format_user_status(status, language) == expected

    @pytest.mark.parametrize("roles_json,language,expected_substrings", [
        ('["applicant", "executor", "manager"]', "ru",
         ["Заявитель", "Исполнитель", "Менеджер"]),
        ('["applicant", "executor", "manager"]', "uz",
         ["Ariza beruvchi", "Ijrochi", "Menejer"]),
        ('["applicant"]', "ru", ["Заявитель"]),
    ])
    def test_roles_localized(self, roles_json, language, expected_substrings):
        result = format_roles(roles_json, language)
        for sub in expected_substrings:
            assert sub in result, f"'{sub}' not in '{result}'"
        # Не должно быть raw key
        assert "roles." not in result
        # Не должно быть raw english value
        for raw in ("applicant", "executor", "manager"):
            assert raw not in result, f"raw '{raw}' оставлен в '{result}'"

    def test_roles_handles_csv_string(self):
        result = format_roles("applicant, executor", "ru")
        assert "Заявитель" in result
        assert "Исполнитель" in result

    def test_roles_handles_list(self):
        result = format_roles(["applicant", "manager"], "ru")
        assert "Заявитель" in result
        assert "Менеджер" in result

    def test_roles_empty_returns_not_specified(self):
        assert format_roles(None, "ru") != "roles."
        assert format_roles("[]", "ru") != ""

    @pytest.mark.parametrize("specs_json,language,expected_substrings,unexpected", [
        ('["plumber", "electrician", "hvac"]', "ru",
         ["Сантехник", "Электрик", "Отопление"],
         ["plumber", "electrician", "hvac"]),
        ('["plumber", "electrician", "hvac"]', "uz",
         ["Santexnik", "Elektrik"],
         ["plumber", "electrician"]),
    ])
    def test_specializations_localized(self, specs_json, language, expected_substrings, unexpected):
        result = format_specializations(specs_json, language)
        for sub in expected_substrings:
            assert sub in result, f"'{sub}' not in '{result}'"
        for raw in unexpected:
            assert raw not in result, f"raw '{raw}' оставлен в '{result}'"
        # Не должно быть JSON-скобок
        assert "[" not in result
        assert "]" not in result

    def test_specializations_full_list(self):
        full = json.dumps([
            "plumber", "electrician", "hvac", "cleaning",
            "security", "maintenance", "installation",
            "repair", "landscaping",
        ])
        result = format_specializations(full, "ru")
        assert "Сантехник" in result
        assert "Электрик" in result
        # Список через запятую, не JSON array
        assert "[" not in result
        assert '"' not in result
