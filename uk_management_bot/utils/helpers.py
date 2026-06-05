import json
import logging
import os
from typing import Dict, Any
from uk_management_bot.config.settings import settings

logger = logging.getLogger(__name__)

# In-memory cache for locale data: {language_code: parsed_dict}
_locale_cache: Dict[str, Dict[str, Any]] = {}


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
        locale = load_locale(language)

        # Handle plural logic if 'count' parameter provided
        plural_key = key
        if 'count' in kwargs:
            count = kwargs['count']
            plural_key = _get_plural_key(key, count, language)

        # Try to get value for plural_key first
        keys = plural_key.split(".")
        value = locale
        found = True

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                found = False
                break

        # If plural key not found, try base key
        if not found and plural_key != key:
            keys = key.split(".")
            value = locale
            found = True

            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    found = False
                    break

        # If still not found, fallback to Russian
        if not found:
            ru_locale = load_locale("ru")
            value = ru_locale

            for ru_k in key.split("."):
                if isinstance(value, dict) and ru_k in value:
                    value = value[ru_k]
                else:
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

def format_request_details(request, locale: Dict[str, Any]) -> str:
    """
    Форматирование деталей заявки

    ОБНОВЛЕНО: Поддержка отображения информации о квартире из справочника
    """
    # Используем новый формат номера заявки
    request_display = request.format_number_for_display()

    details = f"""
📋 {locale.get('requests', {}).get('details', 'Детали заявки')} {request_display}

🏷️ {locale.get('requests', {}).get('category', 'Категория')}: {request.category}
"""

    # НОВОЕ: Отображение адреса с поддержкой справочника
    if hasattr(request, 'apartment_obj') and request.apartment_obj:
        # Заявка привязана к квартире из справочника
        from uk_management_bot.services.address_service import AddressService
        formatted_address = AddressService.format_apartment_address(request.apartment_obj)
        details += f"📍 {locale.get('requests', {}).get('address', 'Адрес')}: {formatted_address} 🏢\n"

        # Дополнительная информация о квартире
        apartment = request.apartment_obj
        if apartment.entrance or apartment.floor or apartment.rooms_count or apartment.area:
            details += f"🏠 {locale.get('requests', {}).get('apartment', 'Квартира')}: "
            apt_details = []
            if apartment.entrance:
                apt_details.append(f"Подъезд {apartment.entrance}")
            if apartment.floor:
                apt_details.append(f"Этаж {apartment.floor}")
            if apartment.rooms_count:
                apt_details.append(f"{apartment.rooms_count} комн.")
            if apartment.area:
                apt_details.append(f"{apartment.area} м²")
            details += ", ".join(apt_details) + "\n"
    else:
        # Legacy: текстовый адрес
        details += f"📍 {locale.get('requests', {}).get('address', 'Адрес')}: {request.address}\n"
        if request.apartment:
            details += f"🏠 {locale.get('requests', {}).get('apartment', 'Квартира')}: {request.apartment}\n"

    details += f"""📝 {locale.get('requests', {}).get('description', 'Описание')}: {request.description}
⚡ {locale.get('requests', {}).get('urgency', 'Срочность')}: {locale.get('urgency', {}).get(request.urgency, request.urgency)}
📊 {locale.get('requests', {}).get('status', 'Статус')}: {request.status}
🕐 {locale.get('requests', {}).get('created_at', 'Создана')}: {request.created_at.strftime('%d.%m.%Y %H:%M')}
"""

    if request.executor:
        details += f"👤 {locale.get('requests', {}).get('executor', 'Исполнитель')}: {request.executor.first_name or request.executor.username or 'Не указан'}\n"

    return details

def format_user_info(user, locale: Dict[str, Any]) -> str:
    """Форматирование информации о пользователе"""
    role_names = {
        "applicant": "Заявитель",
        "executor": "Исполнитель", 
        "manager": "Менеджер"
    }
    
    status_names = {
        "pending": "Ожидает одобрения",
        "approved": "Одобрен",
        "blocked": "Заблокирован"
    }
    
    return f"""
👤 {locale.get('profile', {}).get('title', 'Профиль')}

🆔 ID: {user.telegram_id}
👤 {locale.get('profile', {}).get('role', 'Роль')}: {role_names.get(user.role, user.role)}
📊 {locale.get('profile', {}).get('status', 'Статус')}: {status_names.get(user.status, user.status)}
🌐 {locale.get('profile', {}).get('language', 'Язык')}: {user.language.upper()}
📅 Регистрация: {user.created_at.strftime('%d.%m.%Y')}
"""

def validate_phone(phone: str) -> bool:
    """Валидация номера телефона"""
    import re
    # Простая валидация для узбекских номеров
    pattern = r'^\+998[0-9]{9}$|^998[0-9]{9}$|^[0-9]{9}$'
    return bool(re.match(pattern, phone.replace(' ', '')))

def validate_address(address: str) -> bool:
    """Валидация адреса"""
    return len(address.strip()) >= 10

def validate_description(description: str) -> bool:
    """Валидация описания"""
    return len(description.strip()) >= 10

def format_file_size(size_bytes: int) -> str:
    """Форматирование размера файла"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

def truncate_text(text: str, max_length: int = 100) -> str:
    """Обрезка текста до максимальной длины"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

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

def get_language_from_event(event, db=None):
    """
    Получить язык из Message или CallbackQuery объекта
    
    Args:
        event: Message или CallbackQuery объект
        db: Сессия базы данных (опционально для fallback на БД)
        
    Returns:
        str: Код языка
    """
    # Сначала пробуем language_code из Telegram
    if hasattr(event, 'from_user') and event.from_user:
        telegram_lang = getattr(event.from_user, 'language_code', None)
        if telegram_lang:
            return telegram_lang
        
        # Если нет language_code и есть БД, проверяем пользователя в БД
        if db:
            return get_user_language(event.from_user.id, db)
    
    return "ru"  # fallback


def format_datetime(dt, language: str = "ru") -> str:
    """
    Форматирование datetime объекта в читаемую строку
    
    Args:
        dt: datetime объект
        language: Язык форматирования
        
    Returns:
        str: Отформатированная дата и время
    """
    if not dt:
        return "-"
    
    try:
        if language == "uz":
            return dt.strftime("%d.%m.%Y %H:%M")
        else:  # default to ru
            return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(dt)
