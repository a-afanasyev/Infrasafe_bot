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
