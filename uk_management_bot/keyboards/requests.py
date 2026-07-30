from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Optional
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

def get_discussion_rows(
    request_number: str, *, has_report: bool = False, language: str = "ru"
) -> List[List[InlineKeyboardButton]]:
    """Строки «обсуждение заявки»: комментарии и отчёт (DEAD-134).

    Хендлеры `view_comments_` / `add_comment_` / `view_report_` были написаны
    целиком, но ни одна живая клавиатура их не предлагала: кнопки объявлялись
    только в билдерах с нулём вызовов. Это единственный источник этих строк —
    именно чтобы шестая копия не разошлась с остальными, как разошлись пять
    фолбэков имени (REFACTOR-133).

    Возвращаются СТРОКИ, а не готовая клавиатура: карточки заявки собираются
    по-разному в трёх местах, и каждой нужно вставить их в своё место
    (перед «Назад к списку»).

    `has_report` — показывать ли просмотр отчёта. Кнопка «на всякий случай»
    здесь вредна: хендлер на заявке без отчёта отвечает алертом «отчёта пока
    нет», то есть кнопка обещает то, чего не будет.

    Права НЕ проверяются здесь: их проверяет сам хендлер каноном
    `utils/request_access`. Клавиатура о правах ничего не знает — иначе
    появилась бы вторая, расходящаяся, копия правил доступа.
    """
    rows: List[List[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=get_text("request_assignment.keyboards.view_comments", language=language),
                callback_data=f"view_comments_{request_number}",
            ),
            InlineKeyboardButton(
                text=get_text("request_assignment.keyboards.add_comment", language=language),
                callback_data=f"add_comment_{request_number}",
            ),
        ]
    ]
    if has_report:
        rows.append([
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.view_report", language=language),
                callback_data=f"view_report_{request_number}",
            )
        ])
    return rows


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

