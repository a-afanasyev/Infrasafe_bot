from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Optional
from uk_management_bot.database.session import get_db
import logging
from uk_management_bot.utils.constants import (
    CALLBACK_PREFIX_CATEGORY,
    CALLBACK_PREFIX_URGENCY,
)
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.request_helpers import RequestCallbackHelper

logger = logging.getLogger(__name__)

# Category mapping: internal key -> locale key
CATEGORY_KEYS = {
    "electricity": "categories.electricity",
    "plumbing": "categories.plumbing",
    "heating": "categories.heating",
    "elevator": "categories.elevator",
    "cleaning": "categories.cleaning",
    "landscaping": "categories.landscaping",
    "security": "categories.security",
    "internet": "categories.internet",
}

# Расширенная карта категорий с legacy текстами для обратной совместимости
# TASK 17 Этап A: Нормализация данных категорий
CATEGORY_DEFINITIONS = {
    "electricity": {
        "locale_key": "categories.electricity",
        "legacy_texts": ["Электрика"]
    },
    "plumbing": {
        "locale_key": "categories.plumbing",
        "legacy_texts": ["Сантехника"]
    },
    "heating": {
        "locale_key": "categories.heating",
        "legacy_texts": ["Отопление"]
    },
    "elevator": {
        "locale_key": "categories.elevator",
        "legacy_texts": ["Лифт"]
    },
    "cleaning": {
        "locale_key": "categories.cleaning",
        "legacy_texts": ["Уборка"]
    },
    "landscaping": {
        "locale_key": "categories.landscaping",
        "legacy_texts": ["Благоустройство"]
    },
    "security": {
        "locale_key": "categories.security",
        "legacy_texts": ["Безопасность", "Охрана"]
    },
    "internet": {
        "locale_key": "categories.internet",
        "legacy_texts": ["Интернет/ТВ", "Интернет", "internet_tv"]
    },
    # FS-04: ventilation/other/repair не в бот-меню (CATEGORY_KEYS), но входят в
    # канон для нормализации/отображения web-категорий и legacy-данных.
    "ventilation": {
        "locale_key": "categories.ventilation",
        "legacy_texts": ["Вентиляция"]
    },
    "other": {
        "locale_key": "categories.other",
        "legacy_texts": ["Другое"]
    },
    "repair": {
        "locale_key": "categories.repair",
        "legacy_texts": ["Ремонт"]
    },
}

# List of internal category keys (bot category-selection keyboard — 8 keys)
CATEGORY_INTERNAL_KEYS = list(CATEGORY_KEYS.keys())

# FS-04: полный канонический набор EN-ключей (включает ventilation/other/repair,
# которых нет в бот-меню). Источник истины для нормализации/валидации категории
# на всех каналах записи (бот + web/API) и для миграции legacy RU-лейблов.
CANONICAL_CATEGORY_KEYS = list(CATEGORY_DEFINITIONS.keys())


# TASK 17 Этап A: Helper функции для работы с категориями

def get_category_display(category_key: str, language: str = "ru") -> str:
    """
    Получить локализованное отображаемое название категории по внутреннему ключу.
    
    Args:
        category_key: Внутренний ключ категории (например, "electricity", "plumbing")
        language: Язык интерфейса (ru/uz)
        
    Returns:
        Локализованное название категории или оригинальный ключ, если не найден
        
    Example:
        get_category_display("electricity", "ru") -> "Электрика"
        get_category_display("electricity", "uz") -> "Elektr"
    """
    if category_key in CATEGORY_DEFINITIONS:
        locale_key = CATEGORY_DEFINITIONS[category_key]["locale_key"]
        return get_text(locale_key, language=language)
    
    # Fallback: если ключ не найден, возвращаем оригинальный ключ
    logger.warning(f"Unknown category key: {category_key}, returning as-is")
    return category_key


def resolve_category_key(raw_value: str) -> str:
    """
    Разрешить значение категории (legacy текст или внутренний ключ) в внутренний ключ.
    
    Используется для обратной совместимости со старыми данными в БД,
    где категории могут храниться как русские строки.
    
    Args:
        raw_value: Значение из БД (может быть внутренний ключ или legacy текст)
        
    Returns:
        Внутренний ключ категории или оригинальное значение, если не найдено соответствие
        
    Example:
        resolve_category_key("Электрика") -> "electricity"
        resolve_category_key("electricity") -> "electricity"
        resolve_category_key("unknown") -> "unknown" (с предупреждением в логах)
    """
    # Если это уже канонический ключ (FS-04: полный набор, не только бот-меню)
    if raw_value in CATEGORY_DEFINITIONS:
        return raw_value
    
    # Ищем в legacy текстах
    for internal_key, definition in CATEGORY_DEFINITIONS.items():
        if raw_value in definition.get("legacy_texts", []):
            logger.info(f"Resolved legacy category '{raw_value}' to internal key '{internal_key}'")
            return internal_key
    
    # Если не найдено, логируем предупреждение и возвращаем оригинал
    logger.warning(f"Could not resolve category value '{raw_value}' to internal key, using as-is")
    return raw_value


# Urgency mapping: internal key -> locale key
URGENCY_KEYS = {
    "low": "urgency.low",
    "medium": "urgency.medium",
    "high": "urgency.high",
    "critical": "urgency.critical",
}

# List of internal urgency keys (for use in callbacks)
URGENCY_INTERNAL_KEYS = list(URGENCY_KEYS.keys())


# TASK 17: Helper функция для получения локализованного названия срочности
def get_urgency_display(urgency_key: str, language: str = "ru") -> str:
    """
    Получить локализованное отображаемое название срочности по внутреннему ключу.
    
    Args:
        urgency_key: Внутренний ключ срочности (low, medium, high, critical)
        language: Язык интерфейса (ru/uz)
        
    Returns:
        Локализованное название срочности или оригинальный ключ, если не найден
        
    Example:
        get_urgency_display("low", "ru") -> "Обычная"
        get_urgency_display("low", "uz") -> "Oddiy"
    """
    if urgency_key in URGENCY_KEYS:
        locale_key = URGENCY_KEYS[urgency_key]
        localized = get_text(locale_key, language=language)
        # Если ключ не найден, get_text вернёт сам ключ - используем fallback
        if localized == locale_key:
            logger.warning(f"Locale key '{locale_key}' not found for urgency '{urgency_key}', using original")
            return urgency_key
        return localized
    
    # Fallback: если ключ не найден, возвращаем оригинальный ключ
    logger.warning(f"Unknown urgency key: {urgency_key}, returning as-is")
    return urgency_key


def get_localized_categories(language: str = "ru") -> list:
    """Get list of localized category names

    Args:
        language: Language code (ru/uz)

    Returns:
        List of category names in specified language
    """
    return [get_text(key, language=language) for key in CATEGORY_KEYS.values()]

def get_category_buttons_with_internal_keys(language: str = "ru") -> list:
    """Get list of (display_text, internal_key) tuples for categories

    Args:
        language: Language code (ru/uz)

    Returns:
        List of tuples (localized_text, internal_key)
    """
    return [(get_text(locale_key, language=language), internal_key)
            for internal_key, locale_key in CATEGORY_KEYS.items()]

def get_urgency_buttons_with_internal_keys(language: str = "ru") -> list:
    """Get list of (display_text, internal_key) tuples for urgency levels

    Args:
        language: Language code (ru/uz)

    Returns:
        List of tuples (localized_text, internal_key)
    """
    return [(get_text(locale_key, language=language), internal_key)
            for internal_key, locale_key in URGENCY_KEYS.items()]

def get_categories_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    """Клавиатура с категориями заявок

    Args:
        language: Language code (ru/uz)

    Returns:
        ReplyKeyboardMarkup with localized category buttons
    """
    keyboard = []
    categories = get_localized_categories(language)
    # Размещаем по 2 кнопки в ряду
    for i in range(0, len(categories), 2):
        row = [KeyboardButton(text=categories[i])]
        if i + 1 < len(categories):
            row.append(KeyboardButton(text=categories[i + 1]))
        keyboard.append(row)
    keyboard.append([KeyboardButton(text=get_text("buttons.cancel", language=language))])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_categories_inline_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Inline-клавиатура с категориями заявок (callback_query)

    Args:
        language: Language code (ru/uz)

    Returns:
        InlineKeyboardMarkup with localized category buttons
    """
    keyboard: List[List[InlineKeyboardButton]] = []
    # Раскладываем по 2 в ряд
    row: List[InlineKeyboardButton] = []
    # Use internal keys in callback_data, but display localized text
    category_buttons = get_category_buttons_with_internal_keys(language)
    for idx, (display_text, internal_key) in enumerate(category_buttons):
        row.append(InlineKeyboardButton(
            text=display_text,
            callback_data=f"{CALLBACK_PREFIX_CATEGORY}{internal_key}"
        ))
        if (idx + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_categories_inline_keyboard_with_cancel(language: str = "ru") -> InlineKeyboardMarkup:
    """Inline-клавиатура категорий с кнопкой отмены внизу (для прод-UX).

    Args:
        language: Language code (ru/uz)

    Returns:
        InlineKeyboardMarkup with categories and cancel button
    """
    kb = get_categories_inline_keyboard(language)
    rows = list(kb.inline_keyboard)
    rows.append([InlineKeyboardButton(
        text=get_text("buttons.cancel", language=language),
        callback_data="cancel_create"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_urgency_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    """Клавиатура с уровнями срочности

    Args:
        language: Language code (ru/uz)

    Returns:
        ReplyKeyboardMarkup with urgency buttons
    """
    urgency_buttons = get_urgency_buttons_with_internal_keys(language)
    keyboard = [[KeyboardButton(text=display_text)] for display_text, _ in urgency_buttons]
    keyboard.append([KeyboardButton(text=get_text("buttons.cancel", language=language))])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_urgency_inline_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Inline-клавиатура с уровнями срочности

    Args:
        language: Language code (ru/uz)

    Returns:
        InlineKeyboardMarkup with urgency buttons using internal keys in callback_data
    """
    urgency_buttons = get_urgency_buttons_with_internal_keys(language)
    keyboard = [[InlineKeyboardButton(
        text=display_text,
        callback_data=f"{CALLBACK_PREFIX_URGENCY}{internal_key}"
    )] for display_text, internal_key in urgency_buttons]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_cancel_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены

    Args:
        language: Language code (ru/uz)

    Returns:
        ReplyKeyboardMarkup with cancel button
    """
    keyboard = [
        [KeyboardButton(text=get_text("buttons.cancel", language=language))]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_media_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    """Клавиатура для загрузки медиафайлов

    Args:
        language: Language code (ru/uz)

    Returns:
        ReplyKeyboardMarkup with continue and cancel buttons
    """
    keyboard = [
        [KeyboardButton(text=get_text("buttons.continue", language=language))],
        [KeyboardButton(text=get_text("buttons.cancel", language=language))]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_confirmation_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    """Клавиатура для подтверждения заявки

    Args:
        language: Language code (ru/uz)

    Returns:
        ReplyKeyboardMarkup with confirm, back, and cancel buttons
    """
    keyboard = [
        [KeyboardButton(text=get_text("buttons.confirm", language=language))],
        [KeyboardButton(text=get_text("buttons.back", language=language))],
        [KeyboardButton(text=get_text("buttons.cancel", language=language))]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_inline_confirmation_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Inline-клавиатура подтверждения создания заявки

    Args:
        language: Language code (ru/uz)

    Returns:
        InlineKeyboardMarkup with confirm and cancel buttons
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text=get_text("buttons.confirm", language=language),
                callback_data="confirm_yes"
            ),
            InlineKeyboardButton(
                text=get_text("buttons.cancel", language=language),
                callback_data="confirm_no"
            ),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_edit_request_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    """Клавиатура для редактирования заявки

    Args:
        language: Language code (ru/uz)

    Returns:
        ReplyKeyboardMarkup with localized edit options
    """
    keyboard = [
        [get_text("requests.keyboards.edit_category", language=language)],
        [get_text("requests.keyboards.edit_address", language=language)],
        [get_text("requests.keyboards.edit_description", language=language)],
        [get_text("requests.keyboards.edit_urgency", language=language)],
        [get_text("requests.keyboards.edit_apartment", language=language)],
        [get_text("requests.keyboards.edit_files", language=language)],
        [get_text("buttons.cancel", language=language)]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_request_status_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    """Клавиатура для изменения статуса заявки

    Args:
        language: Language code (ru/uz)

    Returns:
        ReplyKeyboardMarkup with localized status options
    """
    keyboard = [
        [get_text("requests.keyboards.status_to_work", language=language)],
        [get_text("requests.keyboards.status_in_progress", language=language)],
        [get_text("requests.keyboards.status_purchase", language=language)],
        [get_text("requests.keyboards.status_clarification", language=language)],
        [get_text("requests.keyboards.status_completed", language=language)],
        [get_text("requests.keyboards.status_cancel", language=language)],
        [get_text("buttons.back", language=language)]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_requests_filter_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    """Клавиатура для фильтрации заявок

    Args:
        language: Language code (ru/uz)

    Returns:
        ReplyKeyboardMarkup with localized filter options
    """
    keyboard = [
        [get_text("requests.keyboards.filter_all", language=language)],
        [get_text("requests.keyboards.filter_new", language=language)],
        [get_text("requests.keyboards.filter_in_progress", language=language)],
        [get_text("requests.keyboards.filter_purchase", language=language)],
        [get_text("requests.keyboards.filter_completed", language=language)],
        [get_text("requests.keyboards.filter_cancelled", language=language)],
        [get_text("buttons.back", language=language)]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_pagination_keyboard(current_page: int, total_pages: int, request_number: str = None, show_reply_clarify: bool = False, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для пагинации заявок

    TASK 17 Issue #5: Localized pagination keyboard

    Args:
        current_page: Текущая страница
        total_pages: Всего страниц
        request_number: Номер заявки (если нужны кнопки действий)
        show_reply_clarify: Показывать ли кнопку ответа на уточнение
        language: Язык интерфейса (ru/uz)

    Returns:
        InlineKeyboardMarkup с локализованными кнопками
    """
    keyboard = []

    # Кнопки навигации
    nav_buttons = []
    if current_page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"page_{current_page-1}"))

    nav_buttons.append(InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="current_page"))

    if current_page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"page_{current_page+1}"))

    keyboard.append(nav_buttons)

    # Кнопки действий (локализованные)
    if request_number:
        view_text = get_text("buttons.view", language=language)
        edit_text = get_text("buttons.edit", language=language)
        delete_text = get_text("buttons.delete", language=language)

        action_buttons = [
            InlineKeyboardButton(text=f"👁️ {view_text}", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("view_", request_number)),
            InlineKeyboardButton(text=f"✏️ {edit_text}", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("edit_", request_number)),
            InlineKeyboardButton(text=f"🗑️ {delete_text}", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("mgr_delete_", request_number))
        ]
        keyboard.append(action_buttons)
        if show_reply_clarify:
            reply_text = get_text("requests.reply_to_clarification", language=language)
            keyboard.append([InlineKeyboardButton(text=f"💬 {reply_text}", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("replyclarify_", request_number))])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_request_actions_keyboard(request_number: str, language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура действий с заявкой
    
    TASK 17 Этап C: Локализованные кнопки действий
    
    Args:
        request_number: Номер заявки
        language: Язык интерфейса (ru/uz)
    """
    # TASK 17 Этап C: Локализованные тексты кнопок
    view_text = get_text("buttons.view", language=language) or "👁️ Просмотр"
    edit_text = get_text("buttons.edit", language=language) or "✏️ Редактировать"
    accept_text = get_text("buttons.accept", language=language) or "🔧 В работу"
    clarify_text = get_text("buttons.clarify", language=language) or "❓ Уточнение"
    work_text = get_text("buttons.work", language=language) or "🔄 В работу"
    purchase_text = get_text("buttons.purchase", language=language) or "💰 Закуп"
    complete_text = get_text("buttons.complete", language=language) or "✅ Выполнена"
    approve_text = get_text("buttons.approve", language=language) or "✅ Подтвердить"
    cancel_text = get_text("buttons.cancel", language=language) or "❌ Отменить"
    deny_text = get_text("buttons.deny", language=language) or "❌ Отклонить"
    
    keyboard = [
        [
            InlineKeyboardButton(text=view_text, callback_data=RequestCallbackHelper.create_callback_data_with_request_number("view_", request_number)),
            InlineKeyboardButton(text=edit_text, callback_data=RequestCallbackHelper.create_callback_data_with_request_number("edit_", request_number))
        ],
        [
            InlineKeyboardButton(text=accept_text, callback_data=RequestCallbackHelper.create_callback_data_with_request_number("accept_", request_number)),
            InlineKeyboardButton(text=clarify_text, callback_data=RequestCallbackHelper.create_callback_data_with_request_number("clarify_", request_number))
        ],
        [
            InlineKeyboardButton(text=work_text, callback_data=RequestCallbackHelper.create_callback_data_with_request_number("work_", request_number)),
            InlineKeyboardButton(text=purchase_text, callback_data=RequestCallbackHelper.create_callback_data_with_request_number("purchase_", request_number))
        ],
        [
            InlineKeyboardButton(text=complete_text, callback_data=RequestCallbackHelper.create_callback_data_with_request_number("mgr_complete_", request_number)),
            InlineKeyboardButton(text=approve_text, callback_data=RequestCallbackHelper.create_callback_data_with_request_number("approve_", request_number))
        ],
        [
            InlineKeyboardButton(text=cancel_text, callback_data=RequestCallbackHelper.create_callback_data_with_request_number("cancel_", request_number))
        ],
        [
            InlineKeyboardButton(text=deny_text, callback_data=RequestCallbackHelper.create_callback_data_with_request_number("mgr_deny_", request_number))
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# =====================================
# КЛАВИАТУРА ПОШАГОВОГО ВЫБОРА АДРЕСА
# =====================================

PAGE_SIZE_ADDR = 8


def build_request_address_inline_keyboard(addresses: dict, page: int = 0, language: str = "ru") -> InlineKeyboardMarkup:
    """Inline-кнопки выбора адреса заявки (callback `addr:<type>:<id>`).

    План «Обходчик»: вместо свободного текста (глобальный поиск по неуникальному
    `Building.address` мог попасть в чужой дом) — кнопки строго из набора жителя
    (`list_available_request_addresses_sync`). Плоский пагинированный список
    квартиры→дома→дворы; адрес валидируется сервером по id при выборе И при
    сохранении.
    """
    items: list[tuple[str, int, str]] = []
    for a in addresses.get("apartments", []):
        items.append(("apartment", a["id"], f"🏠 {a['label']}"))
    for b in addresses.get("buildings", []):
        items.append(("building", b["id"], f"🏢 {b['label']}"))
    for y in addresses.get("yards", []):
        items.append(("yard", y["id"], f"🏘️ {y['label']}"))

    total = len(items)
    pages = max(1, (total + PAGE_SIZE_ADDR - 1) // PAGE_SIZE_ADDR)
    page = max(0, min(page, pages - 1))
    chunk = items[page * PAGE_SIZE_ADDR:(page + 1) * PAGE_SIZE_ADDR]

    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"addr:{atype}:{aid}")]
        for atype, aid, label in chunk
    ]
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"addr_page:{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="addr_page_noop"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"addr_page:{page + 1}"))
        rows.append(nav)
    rows.append([InlineKeyboardButton(
        text=get_text("buttons.cancel", language=language), callback_data="cancel_create"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_yard_selection_keyboard(user_id: int, language: str = "ru") -> ReplyKeyboardMarkup:
    """
    Создать клавиатуру выбора двора для пользователя (шаг 1)

    Args:
        user_id: Telegram ID пользователя
        language: Language code (ru/uz)

    Returns:
        ReplyKeyboardMarkup: Клавиатура с доступными дворами
    """
    try:
        from uk_management_bot.services.address_service import AddressService

        db_session = next(get_db())
        try:
            # Получаем дворы, в которых у пользователя есть одобренные квартиры
            yards = AddressService.get_user_available_yards(db_session, user_id)
            logger.info(f"Найдено {len(yards)} доступных дворов для пользователя {user_id}")

            # Создаем кнопки для дворов
            yard_buttons = []
            for yard in yards:
                yard_buttons.append([KeyboardButton(text=f"🏘️ {yard.name}")])

            # Добавляем кнопку отмены
            yard_buttons.append([KeyboardButton(text=get_text("buttons.cancel", language=language))])

            return ReplyKeyboardMarkup(keyboard=yard_buttons, resize_keyboard=True)

        finally:
            db_session.close()

    except Exception as e:
        logger.error(f"Ошибка создания клавиатуры дворов для пользователя {user_id}: {e}")
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=get_text("buttons.cancel", language=language))]],
            resize_keyboard=True
        )


def get_building_selection_keyboard(user_id: int, yard_id: int, language: str = "ru") -> ReplyKeyboardMarkup:
    """
    Создать клавиатуру выбора здания в выбранном дворе (шаг 2)

    Args:
        user_id: Telegram ID пользователя
        yard_id: ID выбранного двора
        language: Language code (ru/uz)

    Returns:
        ReplyKeyboardMarkup: Клавиатура с доступными зданиями
    """
    try:
        from uk_management_bot.services.address_service import AddressService

        db_session = next(get_db())
        try:
            # Получаем здания в дворе, где у пользователя есть одобренные квартиры
            buildings = AddressService.get_user_available_buildings(db_session, user_id, yard_id)
            logger.info(f"Найдено {len(buildings)} доступных зданий для пользователя {user_id} в дворе {yard_id}")

            # Создаем кнопки для зданий
            building_buttons = []
            for building in buildings:
                building_buttons.append([KeyboardButton(text=f"🏢 {building.address}")])

            # Добавляем кнопки назад и отмены
            building_buttons.append([KeyboardButton(text=get_text("buttons.back_arrow", language=language))])
            building_buttons.append([KeyboardButton(text=get_text("buttons.cancel", language=language))])

            return ReplyKeyboardMarkup(keyboard=building_buttons, resize_keyboard=True)

        finally:
            db_session.close()

    except Exception as e:
        logger.error(f"Ошибка создания клавиатуры зданий для пользователя {user_id}: {e}")
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=get_text("buttons.cancel", language=language))]],
            resize_keyboard=True
        )


def get_apartment_selection_keyboard(user_id: int, building_id: int, language: str = "ru") -> ReplyKeyboardMarkup:
    """
    Создать клавиатуру выбора квартиры в выбранном здании (шаг 3)

    Args:
        user_id: Telegram ID пользователя
        building_id: ID выбранного здания
        language: Language code (ru/uz)

    Returns:
        ReplyKeyboardMarkup: Клавиатура с доступными квартирами
    """
    try:
        from uk_management_bot.services.address_service import AddressService

        db_session = next(get_db())
        try:
            # Получаем квартиры пользователя в здании
            apartments = AddressService.get_user_available_apartments(db_session, user_id, building_id)
            logger.info(f"Найдено {len(apartments)} доступных квартир для пользователя {user_id} в здании {building_id}")

            # Создаем кнопки для квартир
            apartment_buttons = []
            for apartment in apartments:
                apt_text = get_text("requests.keyboards.apartment_number", language=language).format(num=apartment.apartment_number)
                apartment_buttons.append([KeyboardButton(text=apt_text)])

            # Добавляем кнопки назад и отмены
            apartment_buttons.append([KeyboardButton(text=get_text("buttons.back_arrow", language=language))])
            apartment_buttons.append([KeyboardButton(text=get_text("buttons.cancel", language=language))])

            return ReplyKeyboardMarkup(keyboard=apartment_buttons, resize_keyboard=True)

        finally:
            db_session.close()

    except Exception as e:
        logger.error(f"Ошибка создания клавиатуры квартир для пользователя {user_id}: {e}")
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=get_text("buttons.cancel", language=language))]],
            resize_keyboard=True
        )


# =====================================
# УСТАРЕВШАЯ КЛАВИАТУРА (для обратной совместимости)
# =====================================

def get_address_selection_keyboard(user_id: int, language: str = "ru") -> ReplyKeyboardMarkup:
    """
    Создать динамическую клавиатуру выбора адреса для пользователя

    ОБНОВЛЕНО 13.10.2025: Показывает квартиры, дома и дворы одновременно
    - 🏠 Квартиры (для проблем в квартире)
    - 🏢 Дома (для общедомовых проблем)
    - 🏘️ Дворы (для проблем во дворе)

    Args:
        user_id: Telegram ID пользователя
        language: Language code (ru/uz)

    Returns:
        ReplyKeyboardMarkup: Клавиатура с адресами на трех уровнях

    Raises:
        Exception: При ошибках получения данных пользователя
    """
    try:
        logger.info(f"Создание клавиатуры выбора адреса (квартиры/дома/дворы) для пользователя {user_id}")

        from uk_management_bot.services.address_service import AddressService

        db_session = next(get_db())
        try:
            # Получаем все доступные адреса пользователя
            apartments = AddressService.get_user_approved_apartments_sync(db_session, user_id)
            yards = AddressService.get_user_available_yards(db_session, user_id)

            # Собираем уникальные дома из квартир
            buildings_set = set()
            for apt in apartments:
                if apt.building:
                    buildings_set.add((apt.building.id, apt.building.address, apt.building.yard_id))

            logger.info(f"Найдено для пользователя {user_id}: "
                       f"{len(apartments)} квартир, {len(buildings_set)} домов, {len(yards)} дворов")

            all_buttons = []

            # 1. ДВОРЫ - для проблем во дворе
            if yards:
                for yard in yards:
                    all_buttons.append([KeyboardButton(text=f"🏘️ {yard.name}")])

            # 2. ДОМА - для общедомовых проблем
            if buildings_set:
                for building_id, building_address, yard_id in sorted(buildings_set, key=lambda x: x[1]):
                    all_buttons.append([KeyboardButton(text=f"🏢 {building_address}")])

            # 3. КВАРТИРЫ - для проблем в квартире
            if apartments:
                for apartment in apartments:
                    address_text = AddressService.format_apartment_address(apartment)
                    if len(address_text) > 50:
                        address_text = address_text[:47] + "..."
                    all_buttons.append([KeyboardButton(text=f"🏠 {address_text}")])

            # Кнопка отмены
            all_buttons.append([KeyboardButton(text=get_text("buttons.cancel", language=language))])

            logger.info(f"Создано {len(all_buttons)} кнопок адресов для пользователя {user_id}")

            return ReplyKeyboardMarkup(keyboard=all_buttons, resize_keyboard=True)

        finally:
            db_session.close()

    except Exception as e:
        logger.error(f"Ошибка создания клавиатуры выбора адреса для пользователя {user_id}: {e}")
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=get_text("buttons.cancel", language=language))]],
            resize_keyboard=True
        )


def get_status_filter_inline_keyboard(active_status: Optional[str] = None, language: str = "ru") -> InlineKeyboardMarkup:
    """Упрощённый фильтр: Все, Активные и Архив.

    - Все: все заявки без фильтра
    - Активные: все статусы, кроме финальных
    - Архив: финальные статусы
    
    Args:
        active_status: Текущий активный фильтр (all/active/archive)
        language: Язык интерфейса (ru/uz)
    """
    # Используем локализацию для текстов кнопок
    all_label = get_text("requests.all_requests", language=language)
    active_label = get_text("requests.active_requests_title", language=language)
    archive_label = get_text("requests.archive_title", language=language)

    all_text = f"• {all_label}" if active_status == "all" or active_status is None else all_label
    active_text = f"• {active_label}" if active_status == "active" else active_label
    archive_text = f"• {archive_label}" if active_status == "archive" else archive_label

    buttons = [
        [InlineKeyboardButton(text=all_text, callback_data="status_all")],
        [InlineKeyboardButton(text=active_text, callback_data="status_active")],
        [InlineKeyboardButton(text=archive_text, callback_data="status_archive")],
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_category_filter_inline_keyboard(active_category: Optional[str] = None, language: str = "ru") -> InlineKeyboardMarkup:
    """
    Inline-клавиатура фильтра по категории.
    
    TASK 17 Этап A: Использует внутренние ключи в callback_data и локализованные тексты в labels.
    
    Args:
        active_category: Внутренний ключ активной категории (например, "electricity") или None
        language: Язык интерфейса (ru/uz)
        
    Returns:
        InlineKeyboardMarkup с локализованными кнопками категорий
    """
    buttons = []
    all_label = get_text("requests.all_categories", language) or "Все категории"
    all_text = all_label if not active_category else f"• {all_label}"
    buttons.append([InlineKeyboardButton(text=all_text, callback_data="categoryfilter_all")])

    # Раскладываем категории по 2 в ряд
    # TASK 17 Этап A: Используем внутренние ключи вместо REQUEST_CATEGORIES
    row: List[InlineKeyboardButton] = []
    for idx, internal_key in enumerate(CATEGORY_INTERNAL_KEYS):
        # Получаем локализованное название категории
        display_text = get_category_display(internal_key, language=language)
        # Отмечаем активную категорию
        text = f"• {display_text}" if active_category == internal_key else display_text
        # Используем внутренний ключ в callback_data
        row.append(InlineKeyboardButton(text=text, callback_data=f"categoryfilter_{internal_key}"))
        if (idx + 1) % 2 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_reset_filters_inline_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Кнопка сброса всех фильтров."""
    reset_label = get_text("requests.reset_filters", language) or "Сбросить фильтры"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=reset_label, callback_data="filters_reset")]]
    )


def get_period_filter_inline_keyboard(active_period: Optional[str] = None, language: str = "ru") -> InlineKeyboardMarkup:
    """Inline-клавиатура фильтра по периоду."""
    # Поддерживаемые периоды
    periods = [
        ("all", get_text("requests.period_all", language) or "Все время"),
        ("7d", get_text("requests.period_7d", language) or "7 дней"),
        ("30d", get_text("requests.period_30d", language) or "30 дней"),
        ("90d", get_text("requests.period_90d", language) or "90 дней"),
    ]
    rows: List[List[InlineKeyboardButton]] = []
    for value, label in periods:
        text = f"• {label}" if active_period == value else label
        rows.append([InlineKeyboardButton(text=text, callback_data=f"period_{value}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_executor_filter_inline_keyboard(active_executor: Optional[str] = None, language: str = "ru") -> InlineKeyboardMarkup:
    """Inline-клавиатура фильтра по исполнителю (я/все)."""
    options = [
        ("all", get_text("requests.executor_all", language) or "Все исполнители"),
        ("me", get_text("requests.executor_me", language) or "Я исполнитель"),
    ]
    rows: List[List[InlineKeyboardButton]] = []
    for value, label in options:
        text = f"• {label}" if active_executor == value else label
        rows.append([InlineKeyboardButton(text=text, callback_data=f"executorfilter_{value}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


