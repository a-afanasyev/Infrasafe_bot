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
            KeyboardButton(text=get_text("shifts.accept_shift", language=language) or "🔄 Принять смену"),
            KeyboardButton(text=get_text("shifts.end_shift", language=language) or "🔚 Сдать смену")
        ],
        [
            KeyboardButton(text=get_text("shifts.my_shift", language=language) or "ℹ️ Моя смена"),
            KeyboardButton(text=get_text("shifts.shift_history", language=language) or "📜 История смен")
        ],
        [
            KeyboardButton(text=get_text("buttons.back", language=language) or "🔙 Назад")
        ],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def get_end_shift_confirm_inline(language: str = "ru") -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(text=get_text("shifts.keyboards.confirm_yes", language=language), callback_data="shift_end_confirm_yes"),
        InlineKeyboardButton(text=get_text("shifts.keyboards.confirm_no", language=language), callback_data="shift_end_confirm_no"),
    ]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_shifts_filters_inline(period: Optional[str] = None, status: Optional[str] = None, language: str = "ru") -> InlineKeyboardMarkup:
    period_rows: List[List[InlineKeyboardButton]] = []
    periods = [
        ("all", get_text("shifts.keyboards.period_all_time", language=language)),
        ("today", get_text("shifts.keyboards.period_today", language=language)),
        ("7d", get_text("shifts.keyboards.period_7_days", language=language)),
        ("30d", get_text("shifts.keyboards.period_30_days", language=language)),
        ("90d", get_text("shifts.keyboards.period_90_days", language=language)),
    ]
    for value, label in periods:
        text = f"• {label}" if period == value else label
        period_rows.append([InlineKeyboardButton(text=text, callback_data=f"shifts_period_{value}")])

    status_rows: List[List[InlineKeyboardButton]] = []
    statuses = [
        ("all", get_text("shifts.keyboards.status_all", language=language)),
        ("active", get_text("shifts.keyboards.status_active", language=language)),
        ("completed", get_text("shifts.keyboards.status_completed", language=language)),
        ("cancelled", get_text("shifts.keyboards.status_cancelled", language=language)),
    ]
    for value, label in statuses:
        text = f"• {label}" if status == value else label
        status_rows.append([InlineKeyboardButton(text=text, callback_data=f"shifts_status_{value}")])

    reset_row = [[InlineKeyboardButton(text=get_text("shifts.keyboards.reset_filters", language=language), callback_data="shifts_filters_reset")]]
    return InlineKeyboardMarkup(inline_keyboard=period_rows + status_rows + reset_row)


def get_pagination_inline(current_page: int, total_pages: int, language: str = "ru") -> InlineKeyboardMarkup:
    buttons = []
    row = []
    if current_page > 1:
        row.append(InlineKeyboardButton(text=get_text("shifts.keyboards.page_prev", language=language), callback_data=f"shifts_page_{current_page-1}"))
    row.append(InlineKeyboardButton(text=get_text("shifts.keyboards.page_indicator", language=language).format(current=current_page, total=total_pages), callback_data="shifts_page_current"))
    if current_page < total_pages:
        row.append(InlineKeyboardButton(text=get_text("shifts.keyboards.page_next", language=language), callback_data=f"shifts_page_{current_page+1}"))
    buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_manager_active_shifts_row(telegram_id: int, language: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=get_text("shifts.keyboards.force_end_shift", language=language), callback_data=f"force_end_shift_{telegram_id}")]]
    )


