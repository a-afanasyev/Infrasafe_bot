"""
Сервис генерации и управления номерами заявок в формате YYMMDD-NNN

PR5 (SSOT-кластер #1): единственный генератор номера — атомарный
UPSERT…RETURNING по счётчику дня (request_number_counters). Заменяет три
расходившиеся стратегии (лексикографический MAX — ломался после 999;
COUNT(*)+1 в API/callcenter/inbound_alert — переиспользовал номер после
удаления строки). Счётчик монотонен и gap-safe.

Timezone дневного префикса зафиксирована ЯВНО: Asia/Tashkent (бизнес-дата,
номер видят жители). Раньше date.today() зависел от tz сервера.
"""
import re
import logging
from datetime import date, datetime
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Бизнес-tz дневного префикса YYMMDD (явно; не зависит от tz сервера/контейнера)
BUSINESS_TZ = ZoneInfo("Asia/Tashkent")


def business_today() -> date:
    """Текущая бизнес-дата (Asia/Tashkent) для префикса номера заявки."""
    return datetime.now(BUSINESS_TZ).date()


# Атомарный счётчик дня. Self-seed: при отсутствии строки дня стартуем с
# ЧИСЛОВОГО MAX(suffix) существующих заявок (+1) — покрывает заявки, созданные
# старым кодом до переключения генератора (суффикс начинается с 8-й позиции:
# префикс 'YYMMDD-' = 7 символов). Дальше — чистый инкремент: удаление заявки
# с MAX-суффиксом НЕ приводит к повторной выдаче номера.
# Работает на Postgres и SQLite (3.35+: ON CONFLICT + RETURNING).
_NEXT_SEQ_SQL = text("""
    INSERT INTO request_number_counters (day_prefix, last_seq)
    VALUES (
        :prefix,
        COALESCE((
            SELECT MAX(CAST(SUBSTR(request_number, 8) AS INTEGER))
            FROM requests
            WHERE request_number LIKE :pattern
        ), 0) + 1
    )
    ON CONFLICT (day_prefix)
    DO UPDATE SET last_seq = request_number_counters.last_seq + 1
    RETURNING last_seq
""")

# BUG-122: single source of truth for the request-number shape. The sequence is
# 3+ digits so a building can roll past 999 requests/day (YYMMDD-NNN+).
# Consumers (media proxy, cancel/view callback matchers) build their patterns
# from REQUEST_NUMBER_CORE instead of hardcoding `\d{3}`.
REQUEST_NUMBER_CORE = r"\d{6}-\d{3,}"
REQUEST_NUMBER_PATTERN = rf"^{REQUEST_NUMBER_CORE}$"


class RequestNumberService:
    """Сервис для генерации уникальных номеров заявок в формате YYMMDD-NNN"""
    
    def __init__(self, db: Session):
        self.db = db
    
    @staticmethod
    def _format(prefix: str, seq: int) -> str:
        # Padding до 3 цифр; после 999 растёт естественно (BUG-122: формат 3+)
        return f"{prefix}-{seq:03d}"

    @staticmethod
    def _params(creation_date: Optional[date]) -> tuple[str, dict]:
        prefix = (creation_date or business_today()).strftime("%y%m%d")
        return prefix, {"prefix": prefix, "pattern": f"{prefix}-%"}

    @staticmethod
    def next_number(db: Session, creation_date: Optional[date] = None) -> str:
        """Следующий номер заявки (sync). Вызывать в ТОЙ ЖЕ транзакции, что
        и INSERT заявки, без сетевого I/O до commit — row-lock счётчика дня
        держится до конца транзакции.

        Никаких fallback'ов: ошибка БД — это ошибка (time-fallback старой
        версии выдавал коллизионные номера и удалён).
        """
        if db is None:
            raise ValueError("next_number requires a database session")
        prefix, params = RequestNumberService._params(creation_date)
        seq = db.execute(_NEXT_SEQ_SQL, params).scalar_one()
        number = RequestNumberService._format(prefix, seq)
        logger.info(f"Generated request number: {number}")
        return number

    @staticmethod
    async def next_number_async(db: AsyncSession, creation_date: Optional[date] = None) -> str:
        """Async-вариант next_number — в переданной AsyncSession-транзакции."""
        if db is None:
            raise ValueError("next_number_async requires a database session")
        prefix, params = RequestNumberService._params(creation_date)
        result = await db.execute(_NEXT_SEQ_SQL, params)
        number = RequestNumberService._format(prefix, result.scalar_one())
        logger.info(f"Generated request number: {number}")
        return number

    @staticmethod
    def generate_next_number(creation_date: Optional[date] = None, db: Optional[Session] = None) -> str:
        """Deprecated alias → next_number (сохранён для существующих call-sites).

        db ОБЯЗАТЕЛЕН: ветка db=None старой версии возвращала константный
        '-001' и создавала коллизии.
        """
        return RequestNumberService.next_number(db, creation_date)
    
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
        
        # Format: YYMMDD-NNN (3+ digits — supports >999 requests/day). BUG-122:
        # shared shape so write-validation and consumer matchers can't drift.
        if not re.match(REQUEST_NUMBER_PATTERN, request_number):
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