import json
import logging
import os
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# In-memory cache for locale data: {language_code: parsed_dict}
_locale_cache: Dict[str, Dict[str, Any]] = {}

# Язык → язык-родитель для фолбэка перевода (нет файла или ключа); последний
# рубеж для всех — ru. uz_cyrl (узбекская кириллица) без своего перевода
# показывает латиницу, а не русский.
LANGUAGE_FALLBACKS: Dict[str, str] = {"uz_cyrl": "uz"}


def _fallback_chain(language: str) -> List[str]:
    """Цепочка языков для поиска ключа: сам язык, затем его родители."""
    chain: List[str] = []
    while language and language not in chain:
        chain.append(language)
        language = LANGUAGE_FALLBACKS.get(language)
    return chain


def _resolve_locales_dir() -> str:
    """Возвращает абсолютный путь к директории локалей.

    Сначала пробуем путь относительно пакета `uk_management_bot` (работает в тестах и при запуске проекта),
    затем фолбэк на путь относительно текущей рабочей директории (на случай иной конфигурации запуска).
    """
    module_dir = os.path.dirname(__file__)
    project_root = os.path.abspath(os.path.join(module_dir, ".."))  # uk_management_bot
    candidate = os.path.join(project_root, "config", "locales")
    if os.path.isdir(candidate):
        return candidate
    return os.path.join("config", "locales")


def load_locale(language: str = "ru") -> Dict[str, Any]:
    """Загрузка файла локализации по безопасному абсолютному пути с фолбэком на RU. Cached in memory."""
    if language in _locale_cache:
        return _locale_cache[language]

    locales_dir = _resolve_locales_dir()
    locale_file = os.path.join(locales_dir, f"{language}.json")

    if not os.path.exists(locale_file):
        parent = LANGUAGE_FALLBACKS.get(language)
        if parent:
            # Нет своего файла — локаль родителя (uz_cyrl → uz), не русская.
            data = load_locale(parent)
            _locale_cache[language] = data
            return data
        # Фолбэк на русский язык
        locale_file = os.path.join(locales_dir, "ru.json")

    try:
        with open(locale_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            _locale_cache[language] = data
            return data
    except Exception as e:
        logger.error(f"Ошибка загрузки локализации: {e}")
        return {}

def get_text(key: str, language: str = "ru", **kwargs) -> str:
    """
    Получение переведенного текста по ключу с поддержкой множественного числа.

    TASK 17 ENHANCED: Added plural support for Russian and Uzbek languages.

    Args:
        key: Locale key (supports nested keys like "auth.pending")
        language: Language code ('ru' or 'uz')
        **kwargs: Format parameters. Special parameter 'count' triggers plural logic.

    Returns:
        Localized string with parameters substituted

    Plural Support:
        If 'count' parameter is provided, automatically selects plural form:

        Russian plural rules:
            - 1, 21, 31... → key
            - 2-4, 22-24... → key_plural
            - 5-20, 25-30... → key_plural_many

        Uzbek plural rules:
            - 1 → key
            - 2+ → key_plural

    Example:
        get_text("requests.count", language="ru", count=5)
        # Looks for: requests.count_plural_many (if count=5)
        # Fallback to: requests.count if plural key not found
    """
    try:
        # Handle plural logic if 'count' parameter provided
        plural_key = key
        if 'count' in kwargs:
            count = kwargs['count']
            plural_key = _get_plural_key(key, count, language)

        # Цепочка языков (uz_cyrl → uz): в каждом — plural-ключ, затем базовый.
        found = False
        value: Any = None
        for lang in _fallback_chain(language):
            locale = load_locale(lang)
            found, value = _lookup(locale, plural_key)
            if not found and plural_key != key:
                found, value = _lookup(locale, key)
            if found:
                break

        # If still not found, fallback to Russian
        if not found:
            found, value = _lookup(load_locale("ru"), key)
            if not found:
                return key  # Return key if translation not found

        # Замена параметров в тексте
        # BUG-BOT-032 fix: prefer str.format(**kwargs) so format specs like {x:.1f} work.
        # Fallback to simple replace if format raises (e.g., stray '{' in template).
        if isinstance(value, str) and kwargs:
            try:
                value = value.format(**kwargs)
            except (KeyError, ValueError, IndexError):
                for param, replacement in kwargs.items():
                    value = value.replace(f"{{{param}}}", str(replacement))

        result = value if isinstance(value, str) else key
        return result

    except Exception as e:
        logger.error(f"Ошибка в get_text для ключа {key}, язык {language}: {e}")
        return key


def _lookup(locale: Dict[str, Any], key: str) -> Tuple[bool, Any]:
    """Найти вложенный ключ вида ``a.b.c`` в словаре локали."""
    value: Any = locale
    for k in key.split("."):
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            return False, None
    return True, value


def _get_plural_key(base_key: str, count: int, language: str) -> str:
    """
    Get plural key based on count and language rules.

    TASK 17 Phase 1: Helper for plural support in get_text().

    Args:
        base_key: Base locale key
        count: Number for plural selection
        language: Language code

    Returns:
        Plural key variant
    """
    language = LANGUAGE_FALLBACKS.get(language, language)  # uz_cyrl → правила uz
    if language == 'ru':
        return _get_russian_plural_key(base_key, count)
    elif language == 'uz':
        return _get_uzbek_plural_key(base_key, count)
    else:
        return base_key


def _get_russian_plural_key(base_key: str, count: int) -> str:
    """
    Get Russian plural key based on count.

    Russian plural rules:
        1, 21, 31, 41... → base_key
        2, 3, 4, 22, 23, 24... → base_key_plural
        5-20, 25-30, 35-40... → base_key_plural_many
    """
    abs_count = abs(count)
    last_digit = abs_count % 10
    last_two_digits = abs_count % 100

    # 11-14 are exceptions
    if 11 <= last_two_digits <= 14:
        return f"{base_key}_plural_many"

    # 1, 21, 31...
    if last_digit == 1:
        return base_key

    # 2-4, 22-24...
    if 2 <= last_digit <= 4:
        return f"{base_key}_plural"

    # 5-20, 25-30...
    return f"{base_key}_plural_many"


def _get_uzbek_plural_key(base_key: str, count: int) -> str:
    """
    Get Uzbek plural key based on count.

    Uzbek plural rules (simpler than Russian):
        1 → base_key
        2+ → base_key_plural
    """
    if abs(count) == 1:
        return base_key
    else:
        return f"{base_key}_plural"

def validate_phone(phone: str) -> bool:
    """Валидация номера телефона"""
    import re
    # Простая валидация для узбекских номеров
    pattern = r'^\+998[0-9]{9}$|^998[0-9]{9}$|^[0-9]{9}$'
    return bool(re.match(pattern, phone.replace(' ', '')))

def validate_description(description: str) -> bool:
    """Валидация описания"""
    return len(description.strip()) >= 10

def get_user_language(user_id: int, db) -> str:
    """
    Получить язык пользователя по его telegram ID
    
    Args:
        user_id: Telegram ID пользователя
        db: Сессия базы данных
        
    Returns:
        str: Код языка пользователя или "ru" как fallback
    """
    try:
        from uk_management_bot.database.models.user import User
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if user and user.language:
            return user.language
    except Exception:
        pass
    return "ru"  # fallback
