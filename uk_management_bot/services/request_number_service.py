"""
Сервис генерации и управления номерами заявок в формате YYMMDD-NNN
"""
import re
import logging
from datetime import date, datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

class RequestNumberService:
    """Сервис для генерации уникальных номеров заявок в формате YYMMDD-NNN"""
    
    def __init__(self, db: Session):
        self.db = db
    
    @staticmethod
    def generate_next_number(creation_date: Optional[date] = None, db: Optional[Session] = None) -> str:
        """
        Генерирует следующий номер заявки в формате YYMMDD-NNN
        
        Args:
            creation_date: Дата создания заявки (по умолчанию - сегодня)
            db: Сессия базы данных
            
        Returns:
            Строка с номером заявки (например: "250917-001")
        """
        if creation_date is None:
            creation_date = date.today()
        
        # Формируем префикс YYMMDD
        date_prefix = creation_date.strftime("%y%m%d")
        
        if db is None:
            logger.warning("DB session not provided to generate_next_number")
            return f"{date_prefix}-001"
        
        try:
            # Находим максимальный номер за этот день
            # Используем raw SQL для лучшей производительности
            result = db.execute(
                text("""
                    SELECT request_number 
                    FROM requests 
                    WHERE request_number LIKE :pattern 
                    ORDER BY request_number DESC 
                    LIMIT 1
                """),
                {"pattern": f"{date_prefix}-%"}
            ).fetchone()
            
            if result:
                # Извлекаем номер из найденной записи
                last_number = result[0]
                sequence = int(last_number.split('-')[1])
                next_sequence = sequence + 1
            else:
                # Первая заявка за день
                next_sequence = 1
            
            # Формируем новый номер с padding до 3 цифр
            new_number = f"{date_prefix}-{next_sequence:03d}"
            
            logger.info(f"Generated request number: {new_number}")
            return new_number
            
        except Exception as e:
            logger.error(f"Error generating request number: {e}")
            # Fallback - генерируем номер на основе времени
            timestamp = datetime.now().strftime("%H%M%S")
            fallback_number = f"{date_prefix}-{timestamp[-3:]}"
            logger.warning(f"Using fallback number: {fallback_number}")
            return fallback_number
    
    @staticmethod
    def parse_request_number(request_number: str) -> Dict[str, Any]:
        """
        Парсит номер заявки и возвращает компоненты
        
        Args:
            request_number: Номер заявки в формате YYMMDD-NNN
            
        Returns:
            Словарь с компонентами номера
        """
        if not RequestNumberService.validate_request_number_format(request_number):
            return {
                "valid": False,
                "error": "Invalid format"
            }
        
        try:
            date_part, sequence_part = request_number.split('-')
            
            # Парсим дату
            year = 2000 + int(date_part[:2])
            month = int(date_part[2:4])
            day = int(date_part[4:6])
            
            # Парсим номер последовательности
            sequence = int(sequence_part)
            
            return {
                "valid": True,
                "year": year,
                "month": month,
                "day": day,
                "date": date(year, month, day),
                "sequence": sequence,
                "date_prefix": date_part,
                "sequence_str": sequence_part
            }
            
        except (ValueError, IndexError) as e:
            return {
                "valid": False,
                "error": f"Parse error: {e}"
            }
    
    @staticmethod
    def validate_request_number_format(request_number: str) -> bool:
        """
        Проверяет корректность формата номера заявки
        
        Args:
            request_number: Номер заявки для проверки
            
        Returns:
            True если формат корректный
        """
        if not isinstance(request_number, str):
            return False
        
        # Регулярное выражение для формата YYMMDD-NNN
        pattern = r'^\d{6}-\d{3}$'
        
        if not re.match(pattern, request_number):
            return False
        
        try:
            # Дополнительная проверка корректности даты
            date_part = request_number[:6]
            year = 2000 + int(date_part[:2])
            month = int(date_part[2:4])
            day = int(date_part[4:6])
            
            # Проверяем валидность даты
            date(year, month, day)
            
            return True
            
        except (ValueError, IndexError):
            return False
    
    def get_requests_by_date(self, target_date: date) -> List[str]:
        """
        Получает все номера заявок за указанную дату
        
        Args:
            target_date: Дата для поиска заявок
            
        Returns:
            Список номеров заявок
        """
        date_prefix = target_date.strftime("%y%m%d")
        
        try:
            result = self.db.execute(
                text("""
                    SELECT request_number 
                    FROM requests 
                    WHERE request_number LIKE :pattern 
                    ORDER BY request_number ASC
                """),
                {"pattern": f"{date_prefix}-%"}
            ).fetchall()
            
            return [row[0] for row in result]
            
        except Exception as e:
            logger.error(f"Error getting requests by date {target_date}: {e}")
            return []
    
    def get_daily_statistics(self, target_date: date) -> Dict[str, Any]:
        """
        Получает статистику заявок за день
        
        Args:
            target_date: Дата для статистики
            
        Returns:
            Словарь со статистикой
        """
        requests = self.get_requests_by_date(target_date)
        
        if not requests:
            return {
                "date": target_date,
                "total_requests": 0,
                "last_sequence": 0,
                "next_available": 1
            }
        
        # Парсим последний номер для получения следующего доступного
        last_request = requests[-1]
        parsed = self.parse_request_number(last_request)
        
        return {
            "date": target_date,
            "total_requests": len(requests),
            "last_sequence": parsed.get("sequence", 0),
            "next_available": parsed.get("sequence", 0) + 1,
            "requests": requests
        }
    
    @staticmethod
    def format_for_display(request_number: str) -> str:
        """
        Форматирует номер заявки для отображения пользователю
        
        Args:
            request_number: Номер заявки
            
        Returns:
            Отформатированная строка
        """
        if not RequestNumberService.validate_request_number_format(request_number):
            return request_number  # Возвращаем как есть если формат неверный
        
        parsed = RequestNumberService.parse_request_number(request_number)
        if not parsed["valid"]:
            return request_number
        
        # Можно добавить дополнительное форматирование
        # Например: "№250917-001 (17.09.2025)"
        date_str = parsed["date"].strftime("%d.%m.%Y")
        return f"№{request_number} ({date_str})"
    
    def check_number_availability(self, request_number: str) -> bool:
        """
        Проверяет доступность номера заявки
        
        Args:
            request_number: Номер для проверки
            
        Returns:
            True если номер доступен
        """
        if not self.validate_request_number_format(request_number):
            return False
        
        try:
            result = self.db.execute(
                text("SELECT 1 FROM requests WHERE request_number = :number LIMIT 1"),
                {"number": request_number}
            ).fetchone()
            
            return result is None  # Доступен если не найден
            
        except Exception as e:
            logger.error(f"Error checking number availability: {e}")
            return False