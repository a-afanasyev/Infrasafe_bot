"""
BUG-BOT-027: callback `view_apartment:<id>` показывал generic ошибку
("Заявка не найдена" / "Ошибка загрузки данных") из-за некорректного
joinedload-выражения, который валил handler в except.

После фикса:
- joinedload использует валидные атрибуты моделей
- handler возвращает "Квартира не найдена" (context-specific) для несуществующего id
- locale ru/uz содержит ключ
"""
from __future__ import annotations

import pytest

from uk_management_bot.utils.helpers import get_text


class TestBugBot027ViewApartment:
    @pytest.mark.parametrize("language,expected", [
        ("ru", "❌ Квартира не найдена"),
        ("uz", "❌ Kvartira topilmadi"),
    ])
    def test_apartment_not_found_localized(self, language: str, expected: str) -> None:
        result = get_text("user_apartments.apartment_not_found", language=language)
        assert result == expected
        # Не должно содержать "Заявка"/"Ariza" (запрос)
        assert "Заявка" not in result
        assert "Ariza" not in result

    def test_joinedload_uses_valid_model_attrs(self) -> None:
        """В коде должны использоваться правильные nested joinedload (Apartment.building → Building.yard)."""
        import inspect
        import re
        from uk_management_bot.handlers import user_apartments

        src = inspect.getsource(user_apartments.view_apartment_details)
        # Снимаем комментарии чтобы не ловить старый паттерн в documentation
        src_code_only = re.sub(r"#[^\n]*", "", src)

        # Старый баговый паттерн больше не должен использоваться как код
        assert "property.mapper.class_" not in src_code_only, (
            "view_apartment_details содержит некорректный joinedload "
            "(UserApartment.apartment.property.mapper.class_.building...)"
        )
        # Правильный паттерн
        assert "Apartment.building" in src_code_only
        assert "Building.yard" in src_code_only
