"""
BUG-BOT-015: Empty-state в `ADDR_RESIDENTS` показывал баговые кнопки `✅ Да` / `❌ Нет`
без вопроса; оба callback идентичны (`addr_apartment_view:1`).

После фикса:
- keyboard содержит ровно одну кнопку — "Назад к квартире"
- callback ведёт на `addr_apartment_view:<id>`
- Локализация ru/uz присутствует
"""
from __future__ import annotations

import pytest

from uk_management_bot.utils.helpers import get_text


class TestBugBot015ResidentsEmptyState:
    @pytest.mark.parametrize("language,expected", [
        ("ru", "◀️ Назад к квартире"),
        ("uz", "◀️ Kvartiraga qaytish"),
    ])
    def test_back_to_apartment_localized(self, language: str, expected: str) -> None:
        """Ключ перевода присутствует в обоих локалях."""
        assert (
            get_text("address_apartments.handlers.back_to_apartment", language=language)
            == expected
        )

    def test_back_to_apartment_no_yes_no_buttons(self) -> None:
        """В фикстуре локали не должно быть `Да`/`Нет` подмен с тем же callback."""
        ru = get_text("address_apartments.handlers.back_to_apartment", language="ru")
        uz = get_text("address_apartments.handlers.back_to_apartment", language="uz")
        # Кнопка имеет смысл "назад", не "да/нет"
        for value in (ru, uz):
            assert "Да" not in value
            assert "Нет" not in value
            assert "Ha" not in value
            assert "Yo'q" not in value
