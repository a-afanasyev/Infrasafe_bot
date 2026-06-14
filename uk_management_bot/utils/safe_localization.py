"""
Утилиты для безопасной работы с локализацией

Предоставляет функции для безопасного получения локализованных строк
с обработкой ошибок и fallback-значениями.
"""

import logging

from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)


def safe_get_text(key: str, language: str = "ru", default: str = None, **kwargs) -> str:
    """
    Безопасное получение локализованной строки с fallback и логированием
    
    Args:
        key: Ключ локализации
        language: Язык
        default: Значение по умолчанию, если ключ не найден
        **kwargs: Параметры для форматирования
        
    Returns:
        Локализованная строка или значение по умолчанию
    """
    try:
        result = get_text(key, language=language, **kwargs)
        # Если ключ не найден, get_text вернет сам ключ
        if result == key:
            if default:
                logger.warning(f"Localization key '{key}' not found for language '{language}', using default")
                return default
            else:
                logger.error(f"Localization key '{key}' not found for language '{language}' and no default provided")
                return key
        return result
    except Exception as e:
        logger.error(f"Error getting localization for key '{key}': {e}")
        return default or key


def safe_get_text_with_fallback(key: str, fallback_key: str, language: str = "ru", **kwargs) -> str:
    """
    Безопасное получение локализованной строки с fallback-ключом
    
    Args:
        key: Основной ключ локализации
        fallback_key: Ключ для использования, если основной не найден
        language: Язык
        **kwargs: Параметры для форматирования
        
    Returns:
        Локализованная строка или строка по fallback-ключу
    """
    try:
        result = get_text(key, language=language, **kwargs)
        # Если ключ не найден, используем fallback
        if result == key:
            logger.warning(f"Localization key '{key}' not found for language '{language}', using fallback '{fallback_key}'")
            return get_text(fallback_key, language=language, **kwargs)
        return result
    except Exception as e:
        logger.error(f"Error getting localization for key '{key}': {e}")
        try:
            return get_text(fallback_key, language=language, **kwargs)
        except Exception as fallback_error:
            logger.error(f"Error getting fallback localization for key '{fallback_key}': {fallback_error}")
            return key


def log_missing_key(key: str, language: str, context: str = None) -> None:
    """
    Логирование отсутствующего ключа локализации
    
    Args:
        key: Отсутствующий ключ
        language: Язык
        context: Контекст использования (опционально)
    """
    context_info = f" in context '{context}'" if context else ""
    logger.warning(f"Missing localization key '{key}' for language '{language}'{context_info}")


def validate_localization_coverage(keys: list, language: str = "ru") -> dict:
    """
    Проверяет наличие ключей локализации для указанного языка
    
    Args:
        keys: Список ключей для проверки
        language: Язык для проверки
        
    Returns:
        Словарь с результатами проверки
    """
    results = {
        "total": len(keys),
        "found": 0,
        "missing": []
    }
    
    for key in keys:
        try:
            result = get_text(key, language=language)
            if result != key:
                results["found"] += 1
            else:
                results["missing"].append(key)
        except Exception:
            results["missing"].append(key)
    
    return results
