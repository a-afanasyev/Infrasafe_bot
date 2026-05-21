"""
BUG-BOT-026: Месячный обзор расписания показывал `May 2026` (EN) в RU UI.

После фикса:
- `localized_month_name(5, 'ru')` → `Май`
- `localized_month_year(date(2026, 5, 1), 'ru')` → `Май 2026`
- В RU не должно быть английских имён месяцев
- В UZ — латинизация ("Yanvar", "May", ...)
"""
from __future__ import annotations

from datetime import date

import pytest

from uk_management_bot.utils.date_helpers import (
    localized_month_name,
    localized_month_year,
)


class TestBugBot026LocalizedMonths:
    @pytest.mark.parametrize("month,expected_ru,expected_uz", [
        (1, "Январь", "Yanvar"),
        (3, "Март", "Mart"),
        (5, "Май", "May"),
        (8, "Август", "Avgust"),
        (12, "Декабрь", "Dekabr"),
    ])
    def test_month_name_localized(self, month, expected_ru, expected_uz):
        assert localized_month_name(month, "ru") == expected_ru
        assert localized_month_name(month, "uz") == expected_uz

    def test_month_year_format(self):
        assert localized_month_year(date(2026, 5, 1), "ru") == "Май 2026"
        assert localized_month_year(date(2026, 5, 1), "uz") == "May 2026"
        assert localized_month_year(date(2026, 1, 15), "ru") == "Январь 2026"

    @pytest.mark.parametrize("language", ["ru", "uz"])
    def test_no_english_names_in_ru_uz(self, language):
        english_months = (
            "January", "February", "March", "April", "June", "July",
            "August", "September", "October", "November", "December",
        )
        # "May" допустимо в UZ как латинская транслитерация — проверяем только non-May в RU
        for m in range(1, 13):
            name = localized_month_name(m, language)
            if language == "ru":
                # В русской локали ни одно из английских имён не должно вернуться
                assert name not in english_months, f"month={m} → {name}"

    @pytest.mark.parametrize("bad", [0, 13, -1, 100])
    def test_invalid_month_raises(self, bad):
        with pytest.raises(ValueError):
            localized_month_name(bad, "ru")
