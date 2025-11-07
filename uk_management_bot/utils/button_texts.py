"""
Button Texts Helper - Single Source of Truth for button texts used in filters

Provides functions to get button texts for all supported languages,
automatically scaling when new languages are added to SUPPORTED_LANGUAGES.

This module serves as the single source of truth for button texts used in
aiogram F.text filters, ensuring synchronization between keyboard generation
and message handlers.

Usage:
    from uk_management_bot.utils.button_texts import get_create_request_texts
    
    CREATE_REQUEST_TEXTS = get_create_request_texts()
    
    @router.message(F.text.in_(CREATE_REQUEST_TEXTS))
    async def start_request_creation(...):
        ...
"""

from typing import List
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.language_helpers import SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE
import logging

logger = logging.getLogger(__name__)


def get_button_texts_for_all_languages(locale_key: str, fallback_text: str = None) -> List[str]:
    """
    Получить тексты кнопки для всех поддерживаемых языков.
    
    Используется для создания фильтров F.text.in_() в handlers.
    Автоматически подхватывает все языки из SUPPORTED_LANGUAGES.
    
    Args:
        locale_key: Ключ локализации (например, "main_menu.create_request")
        fallback_text: Текст для fallback, если локализация не загружена
        
    Returns:
        List[str]: Список текстов кнопки на всех языках
        
    Example:
        texts = get_button_texts_for_all_languages("main_menu.create_request")
        # Returns: ["📝 Создать заявку", "📝 Ariza yaratish"]
        
        # При добавлении 'en' в SUPPORTED_LANGUAGES:
        # Returns: ["📝 Создать заявку", "📝 Ariza yaratish", "📝 Create request"]
    """
    texts = []
    
    try:
        for lang in SUPPORTED_LANGUAGES:
            text = get_text(locale_key, language=lang)
            # Проверяем, что это валидный перевод, а не ключ локализации
            # Ключи локализации обычно содержат точку (например, "main_menu.create_request")
            if text and "." not in text:
                texts.append(text)
        
        # Если ничего не загрузилось, используем fallback
        if not texts:
            if fallback_text:
                logger.warning(f"Failed to load button texts for '{locale_key}', using fallback: '{fallback_text}'")
                texts = [fallback_text]
            else:
                # Пробуем получить хотя бы русский текст
                ru_text = get_text(locale_key, language=DEFAULT_LANGUAGE)
                if ru_text and "." not in ru_text:
                    logger.warning(f"Using default language text for '{locale_key}'")
                    texts = [ru_text]
                else:
                    logger.error(f"Failed to load button texts for '{locale_key}' and no fallback provided")
                    texts = []
    except Exception as e:
        logger.error(f"Error loading button texts for '{locale_key}': {e}", exc_info=True)
        if fallback_text:
            texts = [fallback_text]
        else:
            texts = []
    
    return texts


def _init_button_texts() -> dict:
    """
    Инициализация кэшированных текстов кнопок.
    
    Вызывается один раз при импорте модуля для создания кэша всех основных кнопок.
    Это обеспечивает быстрый доступ к текстам в фильтрах handlers.
    
    Returns:
        dict: Словарь с ключами кнопок и списками текстов на всех языках
    """
    button_texts = {}
    
    # Основные кнопки главного меню
    button_texts['create_request'] = get_button_texts_for_all_languages(
        "main_menu.create_request",
        fallback_text="📝 Создать заявку"
    )
    
    button_texts['my_requests'] = get_button_texts_for_all_languages(
        "main_menu.my_requests",
        fallback_text="📋 Мои заявки"
    )
    
    button_texts['profile'] = get_button_texts_for_all_languages(
        "main_menu.profile",
        fallback_text="👤 Профиль"
    )
    
    button_texts['help'] = get_button_texts_for_all_languages(
        "main_menu.help",
        fallback_text="ℹ️ Помощь"
    )
    
    button_texts['active_requests'] = get_button_texts_for_all_languages(
        "main_menu.active_requests",
        fallback_text="🛠 Активные заявки"
    )
    
    button_texts['archive'] = get_button_texts_for_all_languages(
        "main_menu.archive",
        fallback_text="📦 Архив"
    )
    
    button_texts['shift'] = get_button_texts_for_all_languages(
        "main_menu.shift",
        fallback_text="🔄 Смена"
    )
    
    button_texts['my_shifts'] = get_button_texts_for_all_languages(
        "main_menu.my_shifts",
        fallback_text="📋 Мои смены"
    )
    
    button_texts['switch_role'] = get_button_texts_for_all_languages(
        "main_menu.switch_role",
        fallback_text="🔀 Выбрать роль"
    )
    
    button_texts['admin_panel'] = get_button_texts_for_all_languages(
        "main_menu.admin_panel",
        fallback_text="🔧 Админ панель"
    )
    
    button_texts['acceptance'] = get_button_texts_for_all_languages(
        "main_menu.acceptance",
        fallback_text="✅ Ожидают приёмки"
    )
    
    # Кнопки отмены и назад
    button_texts['cancel'] = get_button_texts_for_all_languages(
        "buttons.cancel",
        fallback_text="❌ Отмена"
    )
    
    button_texts['back'] = get_button_texts_for_all_languages(
        "buttons.back",
        fallback_text="🔙 Назад"
    )
    
    # Кнопки меню смены
    button_texts['accept_shift'] = get_button_texts_for_all_languages(
        "shifts.accept_shift",
        fallback_text="🔄 Принять смену"
    )
    
    button_texts['end_shift'] = get_button_texts_for_all_languages(
        "shifts.end_shift",
        fallback_text="🔚 Сдать смену"
    )
    
    button_texts['my_shift'] = get_button_texts_for_all_languages(
        "shifts.my_shift",
        fallback_text="ℹ️ Моя смена"
    )
    
    button_texts['shift_history'] = get_button_texts_for_all_languages(
        "shifts.shift_history",
        fallback_text="📜 История смен"
    )
    
    # Логирование для отладки
    total_texts = sum(len(texts) for texts in button_texts.values())
    logger.info(f"Initialized button texts cache: {len(button_texts)} button types, {total_texts} total texts")
    
    # Детальное логирование в debug режиме
    if logger.isEnabledFor(logging.DEBUG):
        for key, texts in button_texts.items():
            logger.debug(f"  {key}: {len(texts)} languages - {texts}")
    
    return button_texts


# Инициализация кэша при импорте модуля
# Это обеспечивает вычисление текстов один раз при загрузке модуля,
# что критично для использования в фильтрах aiogram (они вычисляются при регистрации)
BUTTON_TEXTS = _init_button_texts()


# Функции-геттеры для удобного доступа к текстам кнопок

def get_create_request_texts() -> List[str]:
    """
    Получить тексты кнопки 'Создать заявку' для всех языков.
    
    Returns:
        List[str]: Список текстов на всех поддерживаемых языках
        
    Example:
        CREATE_REQUEST_TEXTS = get_create_request_texts()
        # ["📝 Создать заявку", "📝 Ariza yaratish"]
        
        @router.message(F.text.in_(CREATE_REQUEST_TEXTS))
        async def start_request_creation(...):
            ...
    """
    return BUTTON_TEXTS.get('create_request', ["📝 Создать заявку"])


def get_my_requests_texts() -> List[str]:
    """
    Получить тексты кнопки 'Мои заявки' для всех языков.
    
    Returns:
        List[str]: Список текстов на всех поддерживаемых языках
    """
    return BUTTON_TEXTS.get('my_requests', ["📋 Мои заявки"])


def get_profile_texts() -> List[str]:
    """
    Получить тексты кнопки 'Профиль' для всех языков.
    
    Returns:
        List[str]: Список текстов на всех поддерживаемых языках
    """
    return BUTTON_TEXTS.get('profile', ["👤 Профиль"])


def get_help_texts() -> List[str]:
    """
    Получить тексты кнопки 'Помощь' для всех языков.
    
    Returns:
        List[str]: Список текстов на всех поддерживаемых языках
    """
    return BUTTON_TEXTS.get('help', ["ℹ️ Помощь"])


def get_active_requests_texts() -> List[str]:
    """
    Получить тексты кнопки 'Активные заявки' для всех языков.
    
    Returns:
        List[str]: Список текстов на всех поддерживаемых языках
    """
    return BUTTON_TEXTS.get('active_requests', ["🛠 Активные заявки"])


def get_archive_texts() -> List[str]:
    """
    Получить тексты кнопки 'Архив' для всех языков.
    
    Returns:
        List[str]: Список текстов на всех поддерживаемых языках
    """
    return BUTTON_TEXTS.get('archive', ["📦 Архив"])


def get_shift_texts() -> List[str]:
    """
    Получить тексты кнопки 'Смена' для всех языков.
    
    Returns:
        List[str]: Список текстов на всех поддерживаемых языках
    """
    return BUTTON_TEXTS.get('shift', ["🔄 Смена"])


def get_my_shifts_texts() -> List[str]:
    """
    Получить тексты кнопки 'Мои смены' для всех языков.
    
    Returns:
        List[str]: Список текстов на всех поддерживаемых языках
    """
    return BUTTON_TEXTS.get('my_shifts', ["📋 Мои смены"])


def get_switch_role_texts() -> List[str]:
    """
    Получить тексты кнопки 'Выбрать роль' для всех языков.
    
    Returns:
        List[str]: Список текстов на всех поддерживаемых языках
    """
    return BUTTON_TEXTS.get('switch_role', ["🔀 Выбрать роль"])


def get_admin_panel_texts() -> List[str]:
    """
    Получить тексты кнопки 'Админ панель' для всех языков.
    
    Returns:
        List[str]: Список текстов на всех поддерживаемых языках
    """
    return BUTTON_TEXTS.get('admin_panel', ["🔧 Админ панель"])


def get_acceptance_texts() -> List[str]:
    """
    Получить тексты кнопки 'Ожидают приёмки' для всех языков.
    
    Returns:
        List[str]: Список текстов на всех поддерживаемых языках
    """
    return BUTTON_TEXTS.get('acceptance', ["✅ Ожидают приёмки"])


def get_cancel_texts() -> List[str]:
    """
    Получить тексты кнопки 'Отмена' для всех языков.
    
    Returns:
        List[str]: Список текстов на всех поддерживаемых языках
    """
    return BUTTON_TEXTS.get('cancel', ["❌ Отмена"])


def get_back_texts() -> List[str]:
    """
    Получить тексты кнопки 'Назад' для всех языков.
    
    Returns:
        List[str]: Список текстов на всех поддерживаемых языках
    """
    return BUTTON_TEXTS.get('back', ["🔙 Назад"])


def get_accept_shift_texts() -> List[str]:
    """
    Получить тексты кнопки 'Принять смену' для всех языков.
    
    Returns:
        List[str]: Список текстов на всех поддерживаемых языках
    """
    return BUTTON_TEXTS.get('accept_shift', ["🔄 Принять смену"])


def get_end_shift_texts() -> List[str]:
    """
    Получить тексты кнопки 'Сдать смену' для всех языков.
    
    Returns:
        List[str]: Список текстов на всех поддерживаемых языках
    """
    return BUTTON_TEXTS.get('end_shift', ["🔚 Сдать смену"])


def get_my_shift_texts() -> List[str]:
    """
    Получить тексты кнопки 'Моя смена' для всех языков.
    
    Returns:
        List[str]: Список текстов на всех поддерживаемых языках
    """
    return BUTTON_TEXTS.get('my_shift', ["ℹ️ Моя смена"])


def get_shift_history_texts() -> List[str]:
    """
    Получить тексты кнопки 'История смен' для всех языков.
    
    Returns:
        List[str]: Список текстов на всех поддерживаемых языках
    """
    return BUTTON_TEXTS.get('shift_history', ["📜 История смен"])


def get_button_texts(button_key: str) -> List[str]:
    """
    Универсальная функция для получения текстов кнопки по ключу.
    
    Args:
        button_key: Ключ кнопки из BUTTON_TEXTS (например, 'create_request')
        
    Returns:
        List[str]: Список текстов на всех языках или пустой список, если ключ не найден
        
    Example:
        texts = get_button_texts('create_request')
        # ["📝 Создать заявку", "📝 Ariza yaratish"]
    """
    return BUTTON_TEXTS.get(button_key, [])

