"""
Unit тесты для RequestNumberService
"""
import unittest
from datetime import date, datetime
from unittest.mock import Mock, MagicMock
from uk_management_bot.services.request_number_service import RequestNumberService

class TestRequestNumberService(unittest.TestCase):
    
    def setUp(self):
        self.mock_db = Mock()
        self.service = RequestNumberService(self.mock_db)
    
    def test_validate_request_number_format_valid(self):
        """Тест валидации корректных номеров"""
        valid_numbers = [
            "250917-001",
            "241225-999",
            "300101-100"
        ]
        
        for number in valid_numbers:
            with self.subTest(number=number):
                self.assertTrue(RequestNumberService.validate_request_number_format(number))
    
    def test_validate_request_number_format_invalid(self):
        """Тест валидации некорректных номеров"""
        invalid_numbers = [
            "25091-001",     # Короткая дата
            "250917-1",      # Короткий номер
            "250917001",     # Нет разделителя
            "25/09/17-001",  # Неверный формат даты
            "250932-001",    # Несуществующий месяц
            "250900-001",    # Несуществующий день
            "",              # Пустая строка
            None,            # None
            123,             # Не строка
        ]
        
        for number in invalid_numbers:
            with self.subTest(number=number):
                self.assertFalse(RequestNumberService.validate_request_number_format(number))
    
    def test_parse_request_number_valid(self):
        """Тест парсинга корректного номера"""
        number = "250917-042"
        result = RequestNumberService.parse_request_number(number)
        
        self.assertTrue(result["valid"])
        self.assertEqual(result["year"], 2025)
        self.assertEqual(result["month"], 9)
        self.assertEqual(result["day"], 17)
        self.assertEqual(result["sequence"], 42)
        self.assertEqual(result["date"], date(2025, 9, 17))
        self.assertEqual(result["date_prefix"], "250917")
        self.assertEqual(result["sequence_str"], "042")
    
    def test_parse_request_number_invalid(self):
        """Тест парсинга некорректного номера"""
        invalid_numbers = ["invalid", "250932-001", ""]
        
        for number in invalid_numbers:
            with self.subTest(number=number):
                result = RequestNumberService.parse_request_number(number)
                self.assertFalse(result["valid"])
                self.assertIn("error", result)
    
    def test_generate_next_number_first_of_day(self):
        """Тест генерации первого номера за день"""
        test_date = date(2025, 9, 17)
        
        # Мокаем пустой результат (нет заявок за день)
        self.mock_db.execute.return_value.fetchone.return_value = None
        
        number = RequestNumberService.generate_next_number(test_date, self.mock_db)
        
        self.assertEqual(number, "250917-001")
    
    def test_generate_next_number_existing_requests(self):
        """Тест генерации номера при существующих заявках"""
        test_date = date(2025, 9, 17)
        
        # Мокаем результат с существующей заявкой
        mock_result = Mock()
        mock_result.__getitem__ = Mock(return_value="250917-005")
        self.mock_db.execute.return_value.fetchone.return_value = mock_result
        
        number = RequestNumberService.generate_next_number(test_date, self.mock_db)
        
        self.assertEqual(number, "250917-006")
    
    def test_generate_next_number_no_db(self):
        """Тест генерации номера без подключения к БД"""
        test_date = date(2025, 9, 17)
        
        number = RequestNumberService.generate_next_number(test_date, None)
        
        self.assertEqual(number, "250917-001")
    
    def test_format_for_display(self):
        """Тест форматирования номера для отображения"""
        number = "250917-001"
        formatted = RequestNumberService.format_for_display(number)
        
        expected = "№250917-001 (17.09.2025)"
        self.assertEqual(formatted, expected)
    
    def test_format_for_display_invalid(self):
        """Тест форматирования некорректного номера"""
        invalid_number = "invalid"
        formatted = RequestNumberService.format_for_display(invalid_number)
        
        # Должен вернуть как есть
        self.assertEqual(formatted, invalid_number)
    
    def test_get_requests_by_date(self):
        """Тест получения заявок за дату"""
        test_date = date(2025, 9, 17)
        
        # Мокаем результат запроса
        mock_rows = [
            ("250917-001",),
            ("250917-002",),
            ("250917-003",)
        ]
        self.mock_db.execute.return_value.fetchall.return_value = mock_rows
        
        requests = self.service.get_requests_by_date(test_date)
        
        expected = ["250917-001", "250917-002", "250917-003"]
        self.assertEqual(requests, expected)
    
    def test_get_daily_statistics_no_requests(self):
        """Тест статистики за день без заявок"""
        test_date = date(2025, 9, 17)
        
        # Мокаем пустой результат
        self.mock_db.execute.return_value.fetchall.return_value = []
        
        stats = self.service.get_daily_statistics(test_date)
        
        self.assertEqual(stats["total_requests"], 0)
        self.assertEqual(stats["next_available"], 1)
        self.assertEqual(stats["date"], test_date)
    
    def test_get_daily_statistics_with_requests(self):
        """Тест статистики за день с заявками"""
        test_date = date(2025, 9, 17)
        
        # Мокаем результат с заявками
        mock_rows = [
            ("250917-001",),
            ("250917-002",),
            ("250917-005",)
        ]
        self.mock_db.execute.return_value.fetchall.return_value = mock_rows
        
        stats = self.service.get_daily_statistics(test_date)
        
        self.assertEqual(stats["total_requests"], 3)
        self.assertEqual(stats["last_sequence"], 5)
        self.assertEqual(stats["next_available"], 6)
        self.assertEqual(len(stats["requests"]), 3)
    
    def test_check_number_availability_available(self):
        """Тест проверки доступности номера - доступен"""
        # Мокаем пустой результат (номер доступен)
        self.mock_db.execute.return_value.fetchone.return_value = None
        
        available = self.service.check_number_availability("250917-001")
        
        self.assertTrue(available)
    
    def test_check_number_availability_taken(self):
        """Тест проверки доступности номера - занят"""
        # Мокаем результат (номер занят)
        self.mock_db.execute.return_value.fetchone.return_value = (1,)
        
        available = self.service.check_number_availability("250917-001")
        
        self.assertFalse(available)
    
    def test_check_number_availability_invalid_format(self):
        """Тест проверки доступности номера с неверным форматом"""
        available = self.service.check_number_availability("invalid")
        
        self.assertFalse(available)

if __name__ == "__main__":
    unittest.main()