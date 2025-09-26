from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Optional
import re
from uk_management_bot.services.auth_service import AuthService
from uk_management_bot.database.session import get_db
from uk_management_bot.utils.constants import ADDRESS_TYPE_DISPLAYS
from uk_management_bot.utils.address_helpers import get_address_type_from_display
import logging
from uk_management_bot.utils.constants import (
    REQUEST_CATEGORIES,
    CALLBACK_PREFIX_CATEGORY,
    CALLBACK_PREFIX_URGENCY,
    REQUEST_URGENCIES,
)
from uk_management_bot.utils.constants import REQUEST_STATUSES
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.request_helpers import RequestCallbackHelper

logger = logging.getLogger(__name__)

def get_categories_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с категориями заявок (единые тексты из REQUEST_CATEGORIES)"""
    keyboard = []
    categories = REQUEST_CATEGORIES
    # Размещаем по 2 кнопки в ряду
    for i in range(0, len(categories), 2):
        row = [KeyboardButton(text=categories[i])]
        if i + 1 < len(categories):
            row.append(KeyboardButton(text=categories[i + 1]))
        keyboard.append(row)
    keyboard.append([KeyboardButton(text="❌ Отмена")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_categories_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline-клавиатура с категориями заявок (callback_query)"""
    keyboard: List[List[InlineKeyboardButton]] = []
    # Раскладываем по 2 в ряд
    row: List[InlineKeyboardButton] = []
    for idx, category in enumerate(REQUEST_CATEGORIES):
        row.append(InlineKeyboardButton(text=category, callback_data=f"{CALLBACK_PREFIX_CATEGORY}{category}"))
        if (idx + 1) % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_categories_inline_keyboard_with_cancel() -> InlineKeyboardMarkup:
    """Inline-клавиатура категорий с кнопкой отмены внизу (для прод-UX)."""
    kb = get_categories_inline_keyboard()
    rows = list(kb.inline_keyboard)
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_create")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_urgency_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с уровнями срочности (единые тексты из REQUEST_URGENCIES)"""
    keyboard = [[KeyboardButton(text=urgency)] for urgency in REQUEST_URGENCIES]
    keyboard.append([KeyboardButton(text="❌ Отмена")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_urgency_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline-клавиатура с уровнями срочности (REQUEST_URGENCIES)"""
    keyboard = [[InlineKeyboardButton(text=urgency, callback_data=f"{CALLBACK_PREFIX_URGENCY}{urgency}")] for urgency in REQUEST_URGENCIES]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопкой отмены"""
    keyboard = [
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_media_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для загрузки медиафайлов"""
    keyboard = [
        [KeyboardButton(text="▶️ Продолжить")],
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_confirmation_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для подтверждения заявки"""
    keyboard = [
        [KeyboardButton(text="✅ Подтвердить")],
        [KeyboardButton(text="🔙 Назад")],
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_inline_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Inline-клавиатура подтверждения создания заявки"""
    keyboard = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_yes"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="confirm_no"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_edit_request_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для редактирования заявки"""
    keyboard = [
        ["🏷️ Изменить категорию"],
        ["📍 Изменить адрес"],
        ["📝 Изменить описание"],
        ["⚡ Изменить срочность"],
        ["🏠 Изменить квартиру"],
        ["📸 Изменить файлы"],
        ["❌ Отмена"]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_request_status_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для изменения статуса заявки"""
    keyboard = [
        ["🔧 В работу"],
        ["🔄 В работе"],
        ["💰 Закуп"],
        ["❓ Уточнение"],
        ["✅ Выполнена"],
        ["❌ Отменить"],
        ["🔙 Назад"]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_requests_filter_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для фильтрации заявок"""
    keyboard = [
        ["📋 Все заявки"],
        ["🆕 Новые"],
        ["🔄 В работе"],
        ["💰 Закуп"],
        ["✅ Выполненные"],
        ["❌ Отмененные"],
        ["🔙 Назад"]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_pagination_keyboard(current_page: int, total_pages: int, request_number: str = None, show_reply_clarify: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для пагинации заявок"""
    keyboard = []
    
    # Кнопки навигации
    nav_buttons = []
    if current_page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"page_{current_page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="current_page"))
    
    if current_page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"page_{current_page+1}"))
    
    keyboard.append(nav_buttons)
    
    # Кнопки действий
    if request_number:
        action_buttons = [
            InlineKeyboardButton(text="👁️ Просмотр", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("view_", request_number)),
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("edit_", request_number)),
            InlineKeyboardButton(text="🗑️ Удалить", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("delete_", request_number))
        ]
        keyboard.append(action_buttons)
        if show_reply_clarify:
            keyboard.append([InlineKeyboardButton(text="💬 Ответить на уточнение", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("replyclarify_", request_number))])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_request_actions_keyboard(request_number: str) -> InlineKeyboardMarkup:
    """Клавиатура действий с заявкой"""
    keyboard = [
        [
            InlineKeyboardButton(text="👁️ Просмотр", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("view_", request_number)),
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("edit_", request_number))
        ],
        [
            InlineKeyboardButton(text="🔧 В работу", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("accept_", request_number)),
            InlineKeyboardButton(text="❓ Уточнение", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("clarify_", request_number))
        ],
        [
            InlineKeyboardButton(text="🔄 В работу", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("work_", request_number)),
            InlineKeyboardButton(text="💰 Закуп", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("purchase_", request_number))
        ],
        [
            InlineKeyboardButton(text="✅ Выполнена", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("complete_", request_number)),
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("approve_", request_number))
        ],
        [
            InlineKeyboardButton(text="❌ Отменить", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("cancel_", request_number))
        ],
        [
            InlineKeyboardButton(text="🚫 Предложить отказ", callback_data=RequestCallbackHelper.create_callback_data_with_request_number("deny_", request_number))
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# =====================================
# КЛАВИАТУРА ВЫБОРА АДРЕСА
# =====================================

async def get_address_selection_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """
    Создать динамическую клавиатуру выбора адреса для пользователя
    
    Args:
        user_id: Telegram ID пользователя
        
    Returns:
        ReplyKeyboardMarkup: Клавиатура с адресами пользователя
        
    Raises:
        Exception: При ошибках получения данных пользователя
    """
    try:
        logger.info(f"Создание клавиатуры выбора адреса для пользователя {user_id}")
        
        # Создать экземпляр AuthService с сессией БД
        db_session = next(get_db())
        auth_service = AuthService(db_session)
        
        # Получить доступные адреса пользователя
        logger.info(f"Запрос доступных адресов для пользователя {user_id}")
        available_addresses = await auth_service.get_available_addresses(user_id)
        logger.info(f"Получены адреса: {available_addresses}")
        
        # Создать кнопки для адресов
        address_buttons = _create_address_buttons(available_addresses)
        logger.info(f"Создано кнопок адресов: {len(address_buttons)} строк")
        
        # Добавить кнопки ручного ввода и отмены
        manual_buttons = _get_manual_input_buttons()
        logger.info(f"Добавлены кнопки ручного ввода: {len(manual_buttons)} строк")
        
        # Объединить все кнопки
        all_buttons = address_buttons + manual_buttons
        logger.info(f"Итоговое количество строк клавиатуры: {len(all_buttons)}")
        
        # Создать клавиатуру
        keyboard = ReplyKeyboardMarkup(keyboard=all_buttons, resize_keyboard=True)
        logger.info(f"Клавиатура создана успешно для пользователя {user_id}")
        
        return keyboard
        
    except Exception as e:
        logger.error(f"Ошибка создания клавиатуры выбора адреса для пользователя {user_id}: {e}")
        
        # Fallback клавиатура с базовыми опциями
        fallback_keyboard = [
            [KeyboardButton(text="✏️ Ввести адрес вручную")],
            [KeyboardButton(text="❌ Отмена")]
        ]
        logger.info(f"Возвращена fallback клавиатура для пользователя {user_id}")
        return ReplyKeyboardMarkup(keyboard=fallback_keyboard, resize_keyboard=True)


def get_status_filter_inline_keyboard(active_status: Optional[str] = None, language: str = "ru") -> InlineKeyboardMarkup:
    """Упрощённый фильтр: только Активные и Архив.

    - Активные: все статусы, кроме финальных
    - Архив: финальные статусы
    """
    active_label = "Активные"
    archive_label = "Архив"

    active_text = f"• {active_label}" if active_status == "active" else active_label
    archive_text = f"• {archive_label}" if active_status == "archive" else archive_label

    buttons = [
        [InlineKeyboardButton(text=active_text, callback_data="status_active")],
        [InlineKeyboardButton(text=archive_text, callback_data="status_archive")],
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_category_filter_inline_keyboard(active_category: Optional[str] = None, language: str = "ru") -> InlineKeyboardMarkup:
    """Inline-клавиатура фильтра по категории."""
    buttons = []
    all_label = get_text("requests.all_categories", language) or "Все категории"
    all_text = all_label if not active_category else f"• {all_label}"
    buttons.append([InlineKeyboardButton(text=all_text, callback_data="categoryfilter_all")])

    # Раскладываем категории по 2 в ряд
    row: List[InlineKeyboardButton] = []
    for idx, category in enumerate(REQUEST_CATEGORIES):
        text = f"• {category}" if active_category == category else category
        row.append(InlineKeyboardButton(text=text, callback_data=f"categoryfilter_{category}"))
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


def _create_address_buttons(available_addresses: Dict[str, str]) -> List[List[KeyboardButton]]:
    """
    Создать кнопки для доступных адресов пользователя
    
    Args:
        available_addresses: Словарь адресов от AuthService
        
    Returns:
        List[List[KeyboardButton]]: Список строк кнопок
    """
    buttons = []
    
    if not available_addresses:
        logger.debug("У пользователя нет доступных адресов")
        return buttons
    
    # Создать кнопки для адресов (максимум 2 в строке для лучшей читаемости)
    address_buttons = []
    for address_type, address in available_addresses.items():
        button_text = _format_address_button(address_type, address)
        address_buttons.append(KeyboardButton(text=button_text))
        logger.debug(f"Создана кнопка адреса: {button_text}")
    
    # Разместить кнопки по 2 в строке
    for i in range(0, len(address_buttons), 2):
        row = address_buttons[i:i+2]
        buttons.append(row)
    
    return buttons


def _format_address_button(address_type: str, address: str) -> str:
    """
    Форматировать текст кнопки адреса
    
    Args:
        address_type: Тип адреса (home/apartment/yard)
        address: Адрес пользователя
        
    Returns:
        str: Отформатированный текст кнопки
        
    Example:
        "🏠 Мой дом: ул. Ленина, 1"
    """
    display_name = ADDRESS_TYPE_DISPLAYS.get(address_type, address_type)
    return f"{display_name}: {address}"


def _get_manual_input_buttons() -> List[List[KeyboardButton]]:
    """
    Получить кнопки для ручного ввода и отмены
    
    Returns:
        List[List[KeyboardButton]]: Кнопки ручного ввода и отмены
    """
    return [
        [KeyboardButton(text="✏️ Ввести адрес вручную")],
        [KeyboardButton(text="❌ Отмена")]
    ]


async def parse_selected_address(selected_text: str) -> Dict[str, Optional[str]]:
    """
    Парсить выбранный адрес из текста кнопки
    
    Args:
        selected_text: Текст выбранной кнопки
        
    Returns:
        dict: Структурированные данные о выборе
        
    Example:
        {"type": "predefined", "address_type": "home", "address": "ул. Ленина, 1"}
        {"type": "manual", "address": None}
        {"type": "cancel", "address": None}
    """
    try:
        logger.debug(f"Парсинг выбранного адреса: {selected_text}")
        
        # Проверить специальные случаи
        if selected_text == "✏️ Ввести адрес вручную":
            logger.debug("Выбран ручной ввод адреса")
            return {"type": "manual", "address": None}
        
        if selected_text == "❌ Отмена":
            logger.debug("Выбрана отмена")
            return {"type": "cancel", "address": None}
        
        # Парсинг предустановленного адреса
        # Формат: "🏠 Мой дом: ул. Ленина, 1"
        if ": " in selected_text:
            display_part, address_part = selected_text.split(": ", 1)
            
            # Определяем тип адреса по содержимому display_part
            address_type = None
            if "дом" in display_part.lower():
                address_type = "home"
            elif "квартира" in display_part.lower():
                address_type = "apartment"
            elif "двор" in display_part.lower():
                address_type = "yard"
            
            if address_type:
                logger.debug(f"Парсинг успешен - тип: {address_type}, адрес: {address_part}")
                return {
                    "type": "predefined",
                    "address_type": address_type,
                    "address": address_part
                }
        
        # Если не удалось распарсить - вернуть unknown
        logger.warning(f"Не удалось распарсить выбор: {selected_text}")
        return {"type": "unknown", "address": selected_text}
        
    except Exception as e:
        logger.error(f"Ошибка парсинга выбранного адреса '{selected_text}': {e}")
        return {"type": "error", "address": selected_text}
