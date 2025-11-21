"""
Unit tests for category helper functions

TASK 17 Этап D: Тесты для нормализации категорий
"""
import pytest
from uk_management_bot.keyboards.requests import (
    resolve_category_key,
    get_category_display,
    CATEGORY_INTERNAL_KEYS,
    CATEGORY_DEFINITIONS
)


class TestResolveCategoryKey:
    """Тесты для функции resolve_category_key"""
    
    def test_resolve_internal_key(self):
        """Тест: внутренний ключ возвращается как есть"""
        assert resolve_category_key("electricity") == "electricity"
        assert resolve_category_key("plumbing") == "plumbing"
    
    def test_resolve_legacy_text(self):
        """Тест: legacy текст разрешается в внутренний ключ"""
        assert resolve_category_key("Электрика") == "electricity"
        assert resolve_category_key("Сантехника") == "plumbing"
    
    def test_resolve_unknown_value(self):
        """Тест: неизвестное значение возвращается как есть с предупреждением"""
        result = resolve_category_key("UnknownCategory")
        assert result == "UnknownCategory"
    
    def test_resolve_empty_string(self):
        """Тест: пустая строка возвращается как есть"""
        assert resolve_category_key("") == ""


class TestGetCategoryDisplay:
    """Тесты для функции get_category_display"""
    
    def test_display_internal_key_ru(self):
        """Тест: отображение внутреннего ключа на русском"""
        result = get_category_display("electricity", "ru")
        # Должно вернуть локализованное название или fallback
        assert result in ["Электрика", "electricity"]  # Зависит от наличия ключа в locale
    
    def test_display_internal_key_uz(self):
        """Тест: отображение внутреннего ключа на узбекском"""
        result = get_category_display("electricity", "uz")
        # Должно вернуть локализованное название или fallback
        assert result in ["Elektrik", "electricity"]  # Зависит от наличия ключа в locale
    
    def test_display_all_categories_ru(self):
        """Тест: все категории отображаются на русском"""
        for internal_key in CATEGORY_INTERNAL_KEYS:
            result = get_category_display(internal_key, "ru")
            assert result is not None
            assert isinstance(result, str)
            assert len(result) > 0
    
    def test_display_all_categories_uz(self):
        """Тест: все категории отображаются на узбекском"""
        for internal_key in CATEGORY_INTERNAL_KEYS:
            result = get_category_display(internal_key, "uz")
            assert result is not None
            assert isinstance(result, str)
            assert len(result) > 0
    
    def test_display_unknown_key(self):
        """Тест: неизвестный ключ возвращается как есть"""
        result = get_category_display("unknown_key", "ru")
        assert result == "unknown_key"


class TestCategoryDefinitions:
    """Тесты для структуры CATEGORY_DEFINITIONS"""
    
    def test_all_internal_keys_have_definitions(self):
        """Тест: все внутренние ключи имеют определения"""
        for internal_key in CATEGORY_INTERNAL_KEYS:
            assert internal_key in CATEGORY_DEFINITIONS
            assert "locale_key" in CATEGORY_DEFINITIONS[internal_key]
            assert "legacy_texts" in CATEGORY_DEFINITIONS[internal_key]
    
    def test_legacy_texts_resolve_correctly(self):
        """Тест: все legacy тексты разрешаются в правильные ключи"""
        for internal_key, definition in CATEGORY_DEFINITIONS.items():
            legacy_texts = definition.get("legacy_texts", [])
            for legacy_text in legacy_texts:
                resolved = resolve_category_key(legacy_text)
                assert resolved == internal_key, f"Legacy text '{legacy_text}' should resolve to '{internal_key}', got '{resolved}'"


class TestCategoryIntegration:
    """Интеграционные тесты для категорий"""
    
    def test_legacy_to_display_ru(self):
        """Тест: legacy текст → внутренний ключ → отображение на русском"""
        legacy_text = "Электрика"
        internal_key = resolve_category_key(legacy_text)
        display = get_category_display(internal_key, "ru")
        assert internal_key == "electricity"
        assert display is not None
    
    def test_legacy_to_display_uz(self):
        """Тест: legacy текст → внутренний ключ → отображение на узбекском"""
        legacy_text = "Электрика"
        internal_key = resolve_category_key(legacy_text)
        display = get_category_display(internal_key, "uz")
        assert internal_key == "electricity"
        assert display is not None

