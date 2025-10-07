"""
Bot Gateway Service - Shift Management Keyboards
UK Management Bot

Keyboard builders for shift management interface.
"""

from typing import List, Dict, Any, Optional
from datetime import date, timedelta
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


# ===========================================
# Main Shift Menu
# ===========================================


def get_shift_menu_keyboard(user_role: str, language: str = "ru") -> ReplyKeyboardMarkup:
    """
    Get main shift management menu.

    Args:
        user_role: User role (executor, manager, admin)
        language: Language code (ru or uz)

    Returns:
        Reply keyboard with shift actions
    """
    texts = {
        "ru": {
            "my_shifts": "📅 Мои смены",
            "available_shifts": "🔍 Доступные смены",
            "schedule": "📆 Расписание",
            "availability": "⏰ Доступность",
            "statistics": "📊 Статистика",
            "back": "◀️ Назад",
        },
        "uz": {
            "my_shifts": "📅 Mening smenalarim",
            "available_shifts": "🔍 Mavjud smenalar",
            "schedule": "📆 Jadval",
            "availability": "⏰ Mavjudlik",
            "statistics": "📊 Statistika",
            "back": "◀️ Orqaga",
        },
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = ReplyKeyboardBuilder()

    # My shifts (always available for executors)
    builder.add(KeyboardButton(text=lang_texts["my_shifts"]))

    # Available shifts (executors can take shifts)
    if user_role in ["executor", "manager", "admin"]:
        builder.add(KeyboardButton(text=lang_texts["available_shifts"]))

    # Schedule (all roles)
    builder.add(KeyboardButton(text=lang_texts["schedule"]))

    # Availability (executors manage their availability)
    if user_role in ["executor"]:
        builder.add(KeyboardButton(text=lang_texts["availability"]))

    # Statistics (all roles)
    builder.add(KeyboardButton(text=lang_texts["statistics"]))

    # Back button
    builder.add(KeyboardButton(text=lang_texts["back"]))

    builder.adjust(2, 2, 1, 1)  # 2-2-1-1 layout
    return builder.as_markup(resize_keyboard=True)


# ===========================================
# Shift List & Details
# ===========================================


def get_shift_actions_keyboard(
    shift_id: str,
    shift_status: str,
    is_assigned_to_me: bool,
    user_role: str,
    language: str = "ru",
) -> InlineKeyboardMarkup:
    """
    Get action buttons for a specific shift.

    Args:
        shift_id: Shift UUID
        shift_status: Shift status (scheduled, available, completed, etc.)
        is_assigned_to_me: Whether current user is assigned
        user_role: User role
        language: Language code

    Returns:
        Inline keyboard with available actions
    """
    texts = {
        "ru": {
            "view": "👁 Просмотр",
            "take": "✅ Взять смену",
            "release": "❌ Отказаться",
            "swap": "🔄 Обменять",
            "details": "📋 Детали",
        },
        "uz": {
            "view": "👁 Ko'rish",
            "take": "✅ Olish",
            "release": "❌ Rad etish",
            "swap": "🔄 Almashtirish",
            "details": "📋 Tafsilotlar",
        },
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    # View details (always available)
    builder.add(
        InlineKeyboardButton(text=lang_texts["view"], callback_data=f"shift:view:{shift_id}")
    )

    # Take shift (if available and not assigned)
    if shift_status == "available" and not is_assigned_to_me:
        builder.add(
            InlineKeyboardButton(text=lang_texts["take"], callback_data=f"shift:take:{shift_id}")
        )

    # Release shift (if assigned to me and scheduled)
    if is_assigned_to_me and shift_status == "scheduled":
        builder.add(
            InlineKeyboardButton(
                text=lang_texts["release"], callback_data=f"shift:release:{shift_id}"
            )
        )

    # Swap shift (if assigned to me and scheduled)
    if is_assigned_to_me and shift_status == "scheduled":
        builder.add(
            InlineKeyboardButton(text=lang_texts["swap"], callback_data=f"shift:swap:{shift_id}")
        )

    builder.adjust(1)  # One button per row
    return builder.as_markup()


def get_shift_filter_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Get filter options for shift list.

    Args:
        language: Language code

    Returns:
        Inline keyboard with filter options
    """
    texts = {
        "ru": {
            "all": "📋 Все смены",
            "today": "📅 Сегодня",
            "week": "📆 Эта неделя",
            "month": "🗓 Этот месяц",
            "by_spec": "🔧 По специализации",
        },
        "uz": {
            "all": "📋 Barcha smenalar",
            "today": "📅 Bugun",
            "week": "📆 Bu hafta",
            "month": "🗓 Bu oy",
            "by_spec": "🔧 Mutaxassislik bo'yicha",
        },
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    builder.add(InlineKeyboardButton(text=lang_texts["all"], callback_data="filter:all"))
    builder.add(InlineKeyboardButton(text=lang_texts["today"], callback_data="filter:today"))
    builder.add(InlineKeyboardButton(text=lang_texts["week"], callback_data="filter:week"))
    builder.add(InlineKeyboardButton(text=lang_texts["month"], callback_data="filter:month"))
    builder.add(InlineKeyboardButton(text=lang_texts["by_spec"], callback_data="filter:spec"))

    builder.adjust(2, 2, 1)  # 2-2-1 layout
    return builder.as_markup()


# ===========================================
# Specialization Selection
# ===========================================


def get_specialization_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Get specialization selection keyboard.

    Args:
        language: Language code

    Returns:
        Inline keyboard with specializations
    """
    # Specialization list (same as in main system)
    specializations = {
        "ru": {
            "plumber": "🔧 Сантехник",
            "electrician": "⚡ Электрик",
            "carpenter": "🪚 Плотник",
            "painter": "🎨 Маляр",
            "locksmith": "🔑 Слесарь",
            "cleaner": "🧹 Уборщик",
            "gardener": "🌱 Садовник",
            "hvac": "❄️ HVAC",
            "general": "👷 Общий",
        },
        "uz": {
            "plumber": "🔧 Santexnik",
            "electrician": "⚡ Elektrik",
            "carpenter": "🪚 Duradgor",
            "painter": "🎨 Rassоm",
            "locksmith": "🔑 Qulfchi",
            "cleaner": "🧹 Tozalovchi",
            "gardener": "🌱 Bog'bon",
            "hvac": "❄️ HVAC",
            "general": "👷 Umumiy",
        },
    }

    lang_specs = specializations.get(language, specializations["ru"])
    builder = InlineKeyboardBuilder()

    for spec_code, spec_name in lang_specs.items():
        builder.add(
            InlineKeyboardButton(text=spec_name, callback_data=f"spec:{spec_code}")
        )

    builder.adjust(2)  # 2 buttons per row
    return builder.as_markup()


# ===========================================
# Date Selection
# ===========================================


def get_date_range_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Get quick date range selection keyboard.

    Args:
        language: Language code

    Returns:
        Inline keyboard with date range options
    """
    texts = {
        "ru": {
            "today": "📅 Сегодня",
            "tomorrow": "📆 Завтра",
            "this_week": "📅 Эта неделя",
            "next_week": "📆 Следующая неделя",
            "this_month": "🗓 Этот месяц",
            "custom": "📝 Свой период",
        },
        "uz": {
            "today": "📅 Bugun",
            "tomorrow": "📆 Ertaga",
            "this_week": "📅 Bu hafta",
            "next_week": "📆 Keyingi hafta",
            "this_month": "🗓 Bu oy",
            "custom": "📝 Boshqa davr",
        },
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    today = date.today()

    builder.add(
        InlineKeyboardButton(
            text=lang_texts["today"], callback_data=f"date:{today.isoformat()}:{today.isoformat()}"
        )
    )

    tomorrow = today + timedelta(days=1)
    builder.add(
        InlineKeyboardButton(
            text=lang_texts["tomorrow"],
            callback_data=f"date:{tomorrow.isoformat()}:{tomorrow.isoformat()}",
        )
    )

    # This week (Monday to Sunday)
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    builder.add(
        InlineKeyboardButton(
            text=lang_texts["this_week"],
            callback_data=f"date:{week_start.isoformat()}:{week_end.isoformat()}",
        )
    )

    # Next week
    next_week_start = week_start + timedelta(days=7)
    next_week_end = next_week_start + timedelta(days=6)
    builder.add(
        InlineKeyboardButton(
            text=lang_texts["next_week"],
            callback_data=f"date:{next_week_start.isoformat()}:{next_week_end.isoformat()}",
        )
    )

    # This month
    month_start = today.replace(day=1)
    if today.month == 12:
        month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)

    builder.add(
        InlineKeyboardButton(
            text=lang_texts["this_month"],
            callback_data=f"date:{month_start.isoformat()}:{month_end.isoformat()}",
        )
    )

    builder.add(
        InlineKeyboardButton(text=lang_texts["custom"], callback_data="date:custom")
    )

    builder.adjust(2, 2, 2)  # 2-2-2 layout
    return builder.as_markup()


# ===========================================
# Availability Management
# ===========================================


def get_availability_actions_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Get availability management action keyboard.

    Args:
        language: Language code

    Returns:
        Inline keyboard with availability actions
    """
    texts = {
        "ru": {
            "add_available": "✅ Добавить доступность",
            "add_unavailable": "❌ Отметить недоступность",
            "view": "📋 Мои настройки",
            "remove": "🗑 Удалить настройку",
        },
        "uz": {
            "add_available": "✅ Mavjudlikni qo'shish",
            "add_unavailable": "❌ Mavjud emasligini belgilash",
            "view": "📋 Mening sozlamalarim",
            "remove": "🗑 Sozlamani o'chirish",
        },
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    builder.add(
        InlineKeyboardButton(
            text=lang_texts["add_available"], callback_data="avail:add:available"
        )
    )
    builder.add(
        InlineKeyboardButton(
            text=lang_texts["add_unavailable"], callback_data="avail:add:unavailable"
        )
    )
    builder.add(InlineKeyboardButton(text=lang_texts["view"], callback_data="avail:view"))
    builder.add(InlineKeyboardButton(text=lang_texts["remove"], callback_data="avail:remove"))

    builder.adjust(1)  # One button per row
    return builder.as_markup()


def get_recurring_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Get recurring availability keyboard.

    Args:
        language: Language code

    Returns:
        Inline keyboard for recurring choice
    """
    texts = {
        "ru": {"yes": "✅ Да, повторять еженедельно", "no": "❌ Нет, только эти даты"},
        "uz": {"yes": "✅ Ha, har hafta takrorlash", "no": "❌ Yo'q, faqat bu sanalar"},
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    builder.add(InlineKeyboardButton(text=lang_texts["yes"], callback_data="recurring:yes"))
    builder.add(InlineKeyboardButton(text=lang_texts["no"], callback_data="recurring:no"))

    builder.adjust(1)
    return builder.as_markup()


def get_days_of_week_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Get days of week selection keyboard.

    Args:
        language: Language code

    Returns:
        Inline keyboard for selecting days
    """
    days = {
        "ru": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
        "uz": ["Du", "Se", "Cho", "Pa", "Ju", "Sha", "Ya"],
    }

    lang_days = days.get(language, days["ru"])
    builder = InlineKeyboardBuilder()

    for i, day_name in enumerate(lang_days):
        builder.add(InlineKeyboardButton(text=day_name, callback_data=f"day:{i}"))

    confirm_text = "✅ Подтвердить" if language == "ru" else "✅ Tasdiqlash"
    builder.add(InlineKeyboardButton(text=confirm_text, callback_data="day:confirm"))

    builder.adjust(4, 3, 1)  # 4-3-1 layout
    return builder.as_markup()


# ===========================================
# Confirmation Keyboards
# ===========================================


def get_confirmation_keyboard(
    action: str, item_id: str, language: str = "ru"
) -> InlineKeyboardMarkup:
    """
    Get confirmation keyboard for actions.

    Args:
        action: Action type (take, release, swap, etc.)
        item_id: Item UUID
        language: Language code

    Returns:
        Inline keyboard with confirm/cancel
    """
    texts = {
        "ru": {"confirm": "✅ Подтвердить", "cancel": "❌ Отмена"},
        "uz": {"confirm": "✅ Tasdiqlash", "cancel": "❌ Bekor qilish"},
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    builder.add(
        InlineKeyboardButton(
            text=lang_texts["confirm"], callback_data=f"{action}:confirm:{item_id}"
        )
    )
    builder.add(
        InlineKeyboardButton(text=lang_texts["cancel"], callback_data=f"{action}:cancel:{item_id}")
    )

    builder.adjust(1)
    return builder.as_markup()


# ===========================================
# Pagination
# ===========================================


def get_pagination_keyboard(
    current_page: int,
    total_pages: int,
    callback_prefix: str,
    language: str = "ru",
) -> InlineKeyboardMarkup:
    """
    Get pagination keyboard for shift lists.

    Args:
        current_page: Current page number (0-indexed)
        total_pages: Total number of pages
        callback_prefix: Prefix for callback data (e.g., "shifts:page")
        language: Language code

    Returns:
        Inline keyboard with pagination controls
    """
    builder = InlineKeyboardBuilder()

    # Previous button
    if current_page > 0:
        prev_text = "◀️ Назад" if language == "ru" else "◀️ Orqaga"
        builder.add(
            InlineKeyboardButton(
                text=prev_text, callback_data=f"{callback_prefix}:{current_page - 1}"
            )
        )

    # Page indicator
    page_text = f"📄 {current_page + 1}/{total_pages}"
    builder.add(InlineKeyboardButton(text=page_text, callback_data="page:current"))

    # Next button
    if current_page < total_pages - 1:
        next_text = "Вперёд ▶️" if language == "ru" else "Oldinga ▶️"
        builder.add(
            InlineKeyboardButton(
                text=next_text, callback_data=f"{callback_prefix}:{current_page + 1}"
            )
        )

    builder.adjust(3)  # All buttons in one row
    return builder.as_markup()
