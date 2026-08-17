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
        assert CATEGORY_TO_SPECIALIZATION["heating"] == "heating"
        assert CATEGORY_TO_SPECIALIZATION["elevator"] == "elevator"
        assert CATEGORY_TO_SPECIALIZATION["repair"] == "repair"
        assert CATEGORY_TO_SPECIALIZATION["ventilation"] == "ventilation"

    def test_legacy_russian_keys_mapped_correctly(self):
        assert CATEGORY_TO_SPECIALIZATION["Сантехника"] == "plumber"
        assert CATEGORY_TO_SPECIALIZATION["Электрика"] == "electrician"
        assert CATEGORY_TO_SPECIALIZATION["Благоустройство"] == "landscaping"
        assert CATEGORY_TO_SPECIALIZATION["Уборка"] == "cleaning"
        assert CATEGORY_TO_SPECIALIZATION["Безопасность"] == "security"
        assert CATEGORY_TO_SPECIALIZATION["Охрана"] == "security"
        assert CATEGORY_TO_SPECIALIZATION["Ремонт"] == "repair"
        assert CATEGORY_TO_SPECIALIZATION["Установка"] == "repair"
        assert CATEGORY_TO_SPECIALIZATION["Обслуживание"] == "elevator"
        assert CATEGORY_TO_SPECIALIZATION["HVAC"] == "heating"
        assert CATEGORY_TO_SPECIALIZATION["Отопление"] == "heating"
        assert CATEGORY_TO_SPECIALIZATION["Вентиляция"] == "ventilation"
        assert CATEGORY_TO_SPECIALIZATION["Лифт"] == "elevator"
        assert CATEGORY_TO_SPECIALIZATION["Интернет/ТВ"] == "electrician"

    def test_contains_at_least_twenty_entries(self):
        # 9 internal + 14 legacy Russian = 23 total
        assert len(CATEGORY_TO_SPECIALIZATION) >= 20


class TestGetSpecializationForCategory:
    def test_known_key_returns_correct_specialization(self):
        assert get_specialization_for_category("plumbing") == "plumber"

    def test_known_russian_key_returns_correct_specialization(self):
        assert get_specialization_for_category("Сантехника") == "plumber"

    def test_unknown_key_returns_repair(self):
        assert get_specialization_for_category("unknown_category") == "repair"

    def test_empty_string_returns_repair(self):
        assert get_specialization_for_category("") == "repair"

    def test_case_sensitive_mismatch_returns_repair(self):
        # "plumbing" is known but "Plumbing" (capitalised) is not
        assert get_specialization_for_category("Plumbing") == "repair"

    def test_all_internal_keys_map_into_the_canon(self):
        """Проверка `!= "other"` больше ничего не значила: дефолт стал `repair`,
        а `hvac`/`maintenance`/`installation` ушли из карты — они никогда и не
        были значениями `request.category`, только формой специализации.
        Сверяем по реальным ключам и против канона."""
        from uk_management_bot.constants.specializations import CANONICAL_SET

        internal_keys = [
            "plumbing", "electricity", "landscaping", "cleaning",
            "security", "heating", "ventilation", "elevator", "internet",
            "repair", "other",
        ]
        for key in internal_keys:
            assert key in CATEGORY_TO_SPECIALIZATION, f"нет записи для {key!r}"
            assert CATEGORY_TO_SPECIALIZATION[key] in CANONICAL_SET, key

    def test_all_russian_keys_map_into_the_canon(self):
        from uk_management_bot.constants.specializations import CANONICAL_SET

        russian_keys = [
            "Сантехника", "Электрика", "Благоустройство", "Уборка",
            "Безопасность", "Охрана", "Ремонт", "Установка",
            "Обслуживание", "HVAC", "Отопление", "Вентиляция", "Лифт", "Интернет/ТВ",
        ]
        for key in russian_keys:
            assert key in CATEGORY_TO_SPECIALIZATION, f"нет записи для {key!r}"
            assert CATEGORY_TO_SPECIALIZATION[key] in CANONICAL_SET, key
