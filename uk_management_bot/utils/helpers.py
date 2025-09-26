import json
import os
from typing import Dict, Any
from uk_management_bot.config.settings import settings

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
    """Загрузка файла локализации по безопасному абсолютному пути с фолбэком на RU."""
    locales_dir = _resolve_locales_dir()
    locale_file = os.path.join(locales_dir, f"{language}.json")

    if not os.path.exists(locale_file):
        # Фолбэк на русский язык
        locale_file = os.path.join(locales_dir, "ru.json")

    try:
        with open(locale_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка загрузки локализации: {e}")
        return {}

def get_text(key: str, language: str = "ru", **kwargs) -> str:
    """Получение переведенного текста по ключу"""
    try:
        locale = load_locale(language)
        
        # Поддержка вложенных ключей (например: "auth.pending")
        keys = key.split(".")
        value = locale
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                # Fallback на русский язык
                ru_locale = load_locale("ru")
                for ru_k in keys:
                    if isinstance(ru_locale, dict) and ru_k in ru_locale:
                        ru_locale = ru_locale[ru_k]
                    else:
                        return key  # Возвращаем ключ если перевод не найден
                return ru_locale
        
        # Замена параметров в тексте
        if isinstance(value, str) and kwargs:
            for param, replacement in kwargs.items():
                value = value.replace(f"{{{param}}}", str(replacement))
        
        result = value if isinstance(value, str) else key
        return result
        
    except Exception as e:
        print(f"Ошибка в get_text для ключа {key}, язык {language}: {e}")
        return key

def format_request_details(request, locale: Dict[str, Any]) -> str:
    """Форматирование деталей заявки"""
    # Используем новый формат номера заявки
    request_display = request.format_number_for_display()
    
    details = f"""
📋 {locale.get('requests', {}).get('details', 'Детали заявки')} {request_display}

🏷️ {locale.get('requests', {}).get('category', 'Категория')}: {request.category}
📍 {locale.get('requests', {}).get('address', 'Адрес')}: {request.address}
📝 {locale.get('requests', {}).get('description', 'Описание')}: {request.description}
🏠 {locale.get('requests', {}).get('apartment', 'Квартира')}: {request.apartment or 'Не указана'}
⚡ {locale.get('requests', {}).get('urgency', 'Срочность')}: {request.urgency}
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
