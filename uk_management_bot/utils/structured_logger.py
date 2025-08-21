"""
Структурированное логирование для production environment
"""
import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict, Optional
from config.settings import settings

class StructuredFormatter(logging.Formatter):
    """
    Форматтер для структурированных логов в JSON формате
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Форматирование записи лога в JSON"""
        # Базовые поля
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Добавляем информацию о файле и строке (только для DEBUG)
        if settings.DEBUG:
            log_entry.update({
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName
            })
        
        # Добавляем exception информацию если есть
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Добавляем дополнительные поля из LoggerAdapter
        if hasattr(record, 'user_id'):
            log_entry["user_id"] = record.user_id
        if hasattr(record, 'telegram_id'):
            log_entry["telegram_id"] = record.telegram_id
        if hasattr(record, 'request_id'):
            log_entry["request_id"] = record.request_id
        if hasattr(record, 'action'):
            log_entry["action"] = record.action
        if hasattr(record, 'component'):
            log_entry["component"] = record.component
        
        # Добавляем метаданные
        if hasattr(record, 'metadata'):
            log_entry["metadata"] = record.metadata
        
        return json.dumps(log_entry, ensure_ascii=False)


class SecurityFilter(logging.Filter):
    """
    Фильтр для исключения чувствительной информации из логов
    """
    
    # Паттерны чувствительной информации
    SENSITIVE_PATTERNS = [
        "password",
        "token", 
        "secret",
        "key",
        "credentials",
        "auth",
        "bearer"
    ]
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Фильтрация чувствительной информации"""
        try:
            message = record.getMessage().lower()
            
            # Проверяем на наличие чувствительных паттернов
            for pattern in self.SENSITIVE_PATTERNS:
                if pattern in message:
                    # Заменяем потенциально чувствительную информацию
                    record.msg = "[REDACTED] Sensitive information filtered"
                    record.args = ()
                    break
            
            return True
        except Exception:
            # Если что-то пошло не так с фильтрацией, пропускаем запись
            return True


class StructuredLogger:
    """
    Обертка для structured logging с дополнительным контекстом
    """
    
    def __init__(self, name: str, **context):
        self.logger = logging.getLogger(name)
        self.context = context
    
    def _log(self, level: int, message: str, **kwargs):
        """Внутренний метод для логирования с контекстом"""
        extra = {**self.context, **kwargs}
        self.logger.log(level, message, extra=extra)
    
    def debug(self, message: str, **kwargs):
        """Debug уровень логирования"""
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """Info уровень логирования"""
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Warning уровень логирования"""
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Error уровень логирования"""
        self._log(logging.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Critical уровень логирования"""
        self._log(logging.CRITICAL, message, **kwargs)
    
    def with_context(self, **context) -> 'StructuredLogger':
        """Создание нового логгера с дополнительным контекстом"""
        new_context = {**self.context, **context}
        return StructuredLogger(self.logger.name, **new_context)


def setup_structured_logging():
    """
    Настройка структурированного логирования для production
    """
    # Получаем root logger
    root_logger = logging.getLogger()
    
    # Очищаем существующие handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Создаем handler
    if settings.DEBUG:
        # В режиме разработки - читаемый формат
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    else:
        # В production - структурированный JSON
        handler = logging.StreamHandler(sys.stdout)
        formatter = StructuredFormatter()
        
        # Добавляем фильтр безопасности
        security_filter = SecurityFilter()
        handler.addFilter(security_filter)
    
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    
    # Устанавливаем уровень логирования
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root_logger.setLevel(log_level)
    
    # Настраиваем специфичные логгеры
    setup_specific_loggers()


def setup_specific_loggers():
    """Настройка специфичных логгеров для разных компонентов"""
    
    # Aiogram логи - только WARNING и выше в production
    aiogram_logger = logging.getLogger("aiogram")
    if not settings.DEBUG:
        aiogram_logger.setLevel(logging.WARNING)
    
    # SQLAlchemy логи - только в DEBUG режиме
    sqlalchemy_logger = logging.getLogger("sqlalchemy.engine")
    if settings.DEBUG:
        sqlalchemy_logger.setLevel(logging.INFO)
    else:
        sqlalchemy_logger.setLevel(logging.WARNING)
    
    # Redis логи
    redis_logger = logging.getLogger("aioredis")
    if not settings.DEBUG:
        redis_logger.setLevel(logging.WARNING)


def get_logger(name: str, **context) -> StructuredLogger:
    """
    Получить структурированный логгер с контекстом
    
    Args:
        name: Имя логгера
        **context: Дополнительный контекст для всех логов
        
    Returns:
        StructuredLogger instance
        
    Example:
        logger = get_logger(__name__, component="auth_service")
        logger.info("User logged in", user_id=123, action="login")
    """
    return StructuredLogger(name, **context)


# Предопределенные логгеры для разных компонентов
def get_auth_logger(**context) -> StructuredLogger:
    """Логгер для компонентов авторизации"""
    return get_logger("uk_bot.auth", component="auth", **context)


def get_request_logger(**context) -> StructuredLogger:
    """Логгер для системы заявок"""
    return get_logger("uk_bot.requests", component="requests", **context)


def get_shift_logger(**context) -> StructuredLogger:
    """Логгер для системы смен"""
    return get_logger("uk_bot.shifts", component="shifts", **context)


def get_security_logger(**context) -> StructuredLogger:
    """Логгер для событий безопасности"""
    return get_logger("uk_bot.security", component="security", **context)


def get_performance_logger(**context) -> StructuredLogger:
    """Логгер для метрик производительности"""
    return get_logger("uk_bot.performance", component="performance", **context)


# Декоратор для автоматического логирования функций
def log_function_call(logger: Optional[StructuredLogger] = None, level: str = "debug"):
    """
    Декоратор для автоматического логирования вызовов функций
    
    Args:
        logger: Логгер для использования (по умолчанию создается автоматически)
        level: Уровень логирования (debug, info, warning, error)
    """
    def decorator(func):
        nonlocal logger
        if logger is None:
            logger = get_logger(func.__module__)
        
        def wrapper(*args, **kwargs):
            func_name = func.__name__
            log_method = getattr(logger, level.lower(), logger.debug)
            
            try:
                log_method(f"Function {func_name} called", 
                          function=func_name, 
                          args_count=len(args),
                          kwargs_keys=list(kwargs.keys()))
                
                result = func(*args, **kwargs)
                
                log_method(f"Function {func_name} completed successfully",
                          function=func_name)
                
                return result
                
            except Exception as e:
                logger.error(f"Function {func_name} failed",
                           function=func_name,
                           error=str(e),
                           exception_type=type(e).__name__)
                raise
        
        # Для async функций
        async def async_wrapper(*args, **kwargs):
            func_name = func.__name__
            log_method = getattr(logger, level.lower(), logger.debug)
            
            try:
                log_method(f"Async function {func_name} called",
                          function=func_name,
                          args_count=len(args), 
                          kwargs_keys=list(kwargs.keys()))
                
                result = await func(*args, **kwargs)
                
                log_method(f"Async function {func_name} completed successfully",
                          function=func_name)
                
                return result
                
            except Exception as e:
                logger.error(f"Async function {func_name} failed",
                           function=func_name,
                           error=str(e),
                           exception_type=type(e).__name__)
                raise
        
        # Возвращаем соответствующую обертку
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return wrapper
    
    return decorator


# Инициализация при импорте модуля
setup_structured_logging()
