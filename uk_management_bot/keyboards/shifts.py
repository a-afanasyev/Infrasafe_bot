from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from typing import Optional, List
from uk_management_bot.utils.helpers import get_text


def get_shifts_main_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    """
    Клавиатура меню смены с локализованными кнопками.
    
    Args:
        language: Язык интерфейса (ru/uz)
    
    Returns:
        ReplyKeyboardMarkup: Клавиатура с кнопками меню смены
    """
    rows = [
        [
            KeyboardButton(text=get_text("shifts.accept_shift", language=language, fallback="🔄 Принять смену")),
            KeyboardButton(text=get_text("shifts.end_shift", language=language, fallback="🔚 Сдать смену"))
        ],
        [
            KeyboardButton(text=get_text("shifts.my_shift", language=language, fallback="ℹ️ Моя смена")),
            KeyboardButton(text=get_text("shifts.shift_history", language=language, fallback="📜 История смен"))
        ],
        [
            KeyboardButton(text=get_text("buttons.back", language=language, fallback="🔙 Назад"))
        ],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def get_end_shift_confirm_inline() -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(text="✅ Да", callback_data="shift_end_confirm_yes"),
        InlineKeyboardButton(text="❌ Нет", callback_data="shift_end_confirm_no"),
    ]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_shifts_filters_inline(period: Optional[str] = None, status: Optional[str] = None) -> InlineKeyboardMarkup:
    period_rows: List[List[InlineKeyboardButton]] = []
    periods = [
        ("all", "Все время"),
        ("today", "Сегодня"),
        ("7d", "7 дней"),
        ("30d", "30 дней"),
        ("90d", "90 дней"),
    ]
    for value, label in periods:
        text = f"• {label}" if period == value else label
        period_rows.append([InlineKeyboardButton(text=text, callback_data=f"shifts_period_{value}")])

    status_rows: List[List[InlineKeyboardButton]] = []
    statuses = [
        ("all", "Все статусы"),
        ("active", "Активные"),
        ("completed", "Завершенные"),
        ("cancelled", "Отмененные"),
    ]
    for value, label in statuses:
        text = f"• {label}" if status == value else label
        status_rows.append([InlineKeyboardButton(text=text, callback_data=f"shifts_status_{value}")])

    reset_row = [[InlineKeyboardButton(text="Сбросить фильтры", callback_data="shifts_filters_reset")]]
    return InlineKeyboardMarkup(inline_keyboard=period_rows + status_rows + reset_row)


def get_pagination_inline(current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    if current_page > 1:
        row.append(InlineKeyboardButton(text="◀️", callback_data=f"shifts_page_{current_page-1}"))
    row.append(InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="shifts_page_current"))
    if current_page < total_pages:
        row.append(InlineKeyboardButton(text="▶️", callback_data=f"shifts_page_{current_page+1}"))
    buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_manager_active_shifts_row(telegram_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❗ Завершить смену", callback_data=f"force_end_shift_{telegram_id}")]]
    )


