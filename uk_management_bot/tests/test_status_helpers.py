"""
Unit tests for status helper functions

TASK 17 Этап D: Тесты для локализации статусов
Updated: перенесено на utils/status_display (единственная рабочая реализация)
"""
import pytest
from uk_management_bot.utils.status_display import (
    get_status_display,
    STATUS_DISPLAY_KEYS
)


class TestGetStatusDisplay:
    """Тесты для функции get_status_display"""

    def test_display_status_ru(self):
        """Тест: отображение статуса на русском"""
        result = get_status_display("Новая", "ru")
        assert result == "Новая"

    def test_display_status_uz(self):
        """Тест: отображение статуса на узбекском"""
        result = get_status_display("Новая", "uz")
        assert result == "Yangi"

    def test_display_all_statuses_ru(self):
        """Тест: все статусы отображаются на русском"""
        for status in STATUS_DISPLAY_KEYS.keys():
            result = get_status_display(status, "ru")
            assert result is not None
            assert isinstance(result, str)
            assert len(result) > 0

    def test_display_all_statuses_uz(self):
        """Тест: все статусы отображаются на узбекском"""
        for status in STATUS_DISPLAY_KEYS.keys():
            result = get_status_display(status, "uz")
            assert result is not None
            assert isinstance(result, str)
            assert len(result) > 0
            # Не должен возвращать ключ локализации как fallback
            assert not result.startswith("statuses.")

    def test_display_unknown_status(self):
        """Тест: неизвестный статус возвращается как есть"""
        result = get_status_display("UnknownStatus", "ru")
        assert result == "UnknownStatus"

    def test_display_empty_string(self):
        """Тест: пустая строка возвращается как есть"""
        result = get_status_display("", "ru")
        assert result == ""


class TestStatusDisplayKeys:
    """Тесты для структуры STATUS_DISPLAY_KEYS"""

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
            assert status in STATUS_DISPLAY_KEYS, f"Status '{status}' missing from STATUS_DISPLAY_KEYS"
            assert STATUS_DISPLAY_KEYS[status].startswith("statuses."), f"Invalid locale key for '{status}'"

    def test_status_keys_format(self):
        """Тест: формат ключей локализации корректен"""
        for status, locale_key in STATUS_DISPLAY_KEYS.items():
            assert locale_key.startswith("statuses."), f"Locale key '{locale_key}' should start with 'statuses.'"
            assert len(locale_key) > len("statuses."), f"Locale key '{locale_key}' is too short"
