"""
Unit tests for validators

TASK 17 Этап D: Тесты для валидатора категорий
"""
import pytest
from uk_management_bot.utils.validators import Validator


class TestValidateCategory:
    """Тесты для функции validate_category"""
    
    def test_validate_internal_key_ru(self):
        """Тест: валидация внутреннего ключа на русском"""
        is_valid, message = Validator.validate_category("electricity", "ru")
        assert is_valid is True
        assert "корректна" in message.lower() or "valid" in message.lower()
    
    def test_validate_internal_key_uz(self):
        """Тест: валидация внутреннего ключа на узбекском"""
        is_valid, message = Validator.validate_category("electricity", "uz")
        assert is_valid is True
    
    def test_validate_legacy_text_ru(self):
        """Тест: валидация legacy текста на русском"""
        is_valid, message = Validator.validate_category("Электрика", "ru")
        assert is_valid is True
    
    def test_validate_legacy_text_uz(self):
        """Тест: валидация legacy текста на узбекском"""
        is_valid, message = Validator.validate_category("Электрика", "uz")
        assert is_valid is True
    
    def test_validate_invalid_category_ru(self):
        """Тест: валидация неверной категории на русском"""
        is_valid, message = Validator.validate_category("InvalidCategory", "ru")
        assert is_valid is False
        assert len(message) > 0
    
    def test_validate_invalid_category_uz(self):
        """Тест: валидация неверной категории на узбекском"""
        is_valid, message = Validator.validate_category("InvalidCategory", "uz")
        assert is_valid is False
        assert len(message) > 0
    
    def test_validate_empty_category(self):
        """Тест: валидация пустой категории"""
        is_valid, message = Validator.validate_category("", "ru")
        assert is_valid is False
        assert len(message) > 0
    
    def test_validate_all_internal_keys(self):
        """Тест: все внутренние ключи валидны"""
        from uk_management_bot.keyboards.requests import CATEGORY_INTERNAL_KEYS
        for internal_key in CATEGORY_INTERNAL_KEYS:
            is_valid, message = Validator.validate_category(internal_key, "ru")
            assert is_valid is True, f"Category '{internal_key}' should be valid"
    
    def test_validate_invalid_category_with_malformed_locale(self):
        """
        Тест: валидация неверной категории с неверным форматом в locale файле
        
        Проверяет, что если в locale файле есть строка с плейсхолдерами,
        отличными от {categories}, код не падает с KeyError, а использует fallback.
        """
        # Симулируем ситуацию, когда get_text возвращает строку с неверным форматом
        # Это может произойти, если в locale файле есть другие плейсхолдеры
        from unittest.mock import patch
        
        # Мокаем get_text в модуле helpers, так как он импортируется внутри функции
        with patch('uk_management_bot.utils.helpers.get_text') as mock_get_text:
            # Симулируем строку с неверным форматом (содержит {other} вместо {categories})
            mock_get_text.return_value = "Неверная категория: {categories} и {other}"
            
            # Валидация должна работать без KeyError
            is_valid, message = Validator.validate_category("InvalidCategory", "ru")
            assert is_valid is False
            assert len(message) > 0
            # Сообщение должно содержать fallback формат (простая конкатенация)
            assert "Доступные категории" in message

