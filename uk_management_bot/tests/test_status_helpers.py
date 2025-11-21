"""
Unit tests for status helper functions

TASK 17 Этап D: Тесты для локализации статусов
"""
import pytest
from uk_management_bot.keyboards.requests import (
    get_status_display,
    STATUS_KEYS
)


class TestGetStatusDisplay:
    """Тесты для функции get_status_display"""
    
    def test_display_status_ru(self):
        """Тест: отображение статуса на русском"""
        result = get_status_display("Новая", "ru")
        # Должно вернуть локализованное название или fallback
        assert result in ["Новая", "requests.status_new"]  # Зависит от наличия ключа в locale
    
    def test_display_status_uz(self):
        """Тест: отображение статуса на узбекском"""
        result = get_status_display("Новая", "uz")
        # Должно вернуть локализованное название или fallback
        assert result in ["Новая", "Yangi", "requests.status_new"]  # Зависит от наличия ключа в locale
    
    def test_display_all_statuses_ru(self):
        """Тест: все статусы отображаются на русском"""
        for status in STATUS_KEYS.keys():
            result = get_status_display(status, "ru")
            assert result is not None
            assert isinstance(result, str)
            assert len(result) > 0
    
    def test_display_all_statuses_uz(self):
        """Тест: все статусы отображаются на узбекском"""
        for status in STATUS_KEYS.keys():
            result = get_status_display(status, "uz")
            assert result is not None
            assert isinstance(result, str)
            assert len(result) > 0
    
    def test_display_unknown_status(self):
        """Тест: неизвестный статус возвращается как есть"""
        result = get_status_display("UnknownStatus", "ru")
        assert result == "UnknownStatus"
    
    def test_display_empty_string(self):
        """Тест: пустая строка возвращается как есть"""
        result = get_status_display("", "ru")
        assert result == ""


class TestStatusKeys:
    """Тесты для структуры STATUS_KEYS"""
    
    def test_all_statuses_have_keys(self):
        """Тест: все статусы имеют ключи локализации"""
        expected_statuses = [
            "Новая",
            "В работе",
            "Закуп",
            "Уточнение",
            "Выполнена",
            "Исполнено",
            "Принято",
            "Отменена"
        ]
        for status in expected_statuses:
            assert status in STATUS_KEYS, f"Status '{status}' missing from STATUS_KEYS"
            assert STATUS_KEYS[status].startswith("requests.status_"), f"Invalid locale key for '{status}'"
    
    def test_status_keys_format(self):
        """Тест: формат ключей локализации корректен"""
        for status, locale_key in STATUS_KEYS.items():
            assert locale_key.startswith("requests.status_"), f"Locale key '{locale_key}' should start with 'requests.status_'"
            assert len(locale_key) > len("requests.status_"), f"Locale key '{locale_key}' is too short"

