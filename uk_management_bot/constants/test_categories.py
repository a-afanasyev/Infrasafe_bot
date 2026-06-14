"""Unit tests for uk_management_bot/constants/categories.py."""

from uk_management_bot.constants.categories import (
    CATEGORY_TO_SPECIALIZATION,
    get_specialization_for_category,
)


class TestCategoryToSpecializationDict:
    def test_is_dict(self):
        assert isinstance(CATEGORY_TO_SPECIALIZATION, dict)

    def test_all_values_are_strings(self):
        for key, value in CATEGORY_TO_SPECIALIZATION.items():
            assert isinstance(value, str), f"Expected str for key {key!r}, got {type(value)}"

    def test_known_internal_keys_mapped_correctly(self):
        assert CATEGORY_TO_SPECIALIZATION["plumbing"] == "plumber"
        assert CATEGORY_TO_SPECIALIZATION["electricity"] == "electrician"
        assert CATEGORY_TO_SPECIALIZATION["landscaping"] == "landscaping"
        assert CATEGORY_TO_SPECIALIZATION["cleaning"] == "cleaning"
        assert CATEGORY_TO_SPECIALIZATION["security"] == "security"
        assert CATEGORY_TO_SPECIALIZATION["hvac"] == "hvac"
        assert CATEGORY_TO_SPECIALIZATION["maintenance"] == "maintenance"
        assert CATEGORY_TO_SPECIALIZATION["repair"] == "repair"
        assert CATEGORY_TO_SPECIALIZATION["installation"] == "installation"

    def test_legacy_russian_keys_mapped_correctly(self):
        assert CATEGORY_TO_SPECIALIZATION["Сантехника"] == "plumber"
        assert CATEGORY_TO_SPECIALIZATION["Электрика"] == "electrician"
        assert CATEGORY_TO_SPECIALIZATION["Благоустройство"] == "landscaping"
        assert CATEGORY_TO_SPECIALIZATION["Уборка"] == "cleaning"
        assert CATEGORY_TO_SPECIALIZATION["Безопасность"] == "security"
        assert CATEGORY_TO_SPECIALIZATION["Охрана"] == "security"
        assert CATEGORY_TO_SPECIALIZATION["Ремонт"] == "repair"
        assert CATEGORY_TO_SPECIALIZATION["Установка"] == "installation"
        assert CATEGORY_TO_SPECIALIZATION["Обслуживание"] == "maintenance"
        assert CATEGORY_TO_SPECIALIZATION["HVAC"] == "hvac"
        assert CATEGORY_TO_SPECIALIZATION["Отопление"] == "hvac"
        assert CATEGORY_TO_SPECIALIZATION["Вентиляция"] == "hvac"
        assert CATEGORY_TO_SPECIALIZATION["Лифт"] == "maintenance"
        assert CATEGORY_TO_SPECIALIZATION["Интернет/ТВ"] == "electrician"

    def test_contains_at_least_twenty_entries(self):
        # 9 internal + 14 legacy Russian = 23 total
        assert len(CATEGORY_TO_SPECIALIZATION) >= 20


class TestGetSpecializationForCategory:
    def test_known_key_returns_correct_specialization(self):
        assert get_specialization_for_category("plumbing") == "plumber"

    def test_known_russian_key_returns_correct_specialization(self):
        assert get_specialization_for_category("Сантехника") == "plumber"

    def test_unknown_key_returns_other(self):
        assert get_specialization_for_category("unknown_category") == "other"

    def test_empty_string_returns_other(self):
        assert get_specialization_for_category("") == "other"

    def test_case_sensitive_mismatch_returns_other(self):
        # "plumbing" is known but "Plumbing" (capitalised) is not
        assert get_specialization_for_category("Plumbing") == "other"

    def test_all_internal_keys_return_non_other(self):
        internal_keys = [
            "plumbing", "electricity", "landscaping", "cleaning",
            "security", "hvac", "maintenance", "repair", "installation",
        ]
        for key in internal_keys:
            result = get_specialization_for_category(key)
            assert result != "other", f"Expected real specialization for {key!r}"

    def test_all_russian_keys_return_non_other(self):
        russian_keys = [
            "Сантехника", "Электрика", "Благоустройство", "Уборка",
            "Безопасность", "Охрана", "Ремонт", "Установка",
            "Обслуживание", "HVAC", "Отопление", "Вентиляция", "Лифт", "Интернет/ТВ",
        ]
        for key in russian_keys:
            result = get_specialization_for_category(key)
            assert result != "other", f"Expected real specialization for {key!r}"
