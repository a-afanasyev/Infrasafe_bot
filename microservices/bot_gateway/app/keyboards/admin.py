"""
Bot Gateway Service - Admin Panel Keyboards
UK Management Bot

Keyboard builders for admin panel interface.
"""

from typing import List, Dict, Any, Optional
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


# ===========================================
# Main Admin Menu
# ===========================================


def get_admin_menu_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    """
    Get main admin panel menu.

    Args:
        language: Language code (ru or uz)

    Returns:
        Reply keyboard with admin actions
    """
    texts = {
        "ru": {
            "users": "👥 Пользователи",
            "requests": "📋 Заявки",
            "shifts": "📅 Смены",
            "analytics": "📊 Аналитика",
            "broadcast": "📢 Рассылка",
            "config": "⚙️ Настройки",
            "logs": "📝 Логи",
            "back": "◀️ Назад",
        },
        "uz": {
            "users": "👥 Foydalanuvchilar",
            "requests": "📋 Arizalar",
            "shifts": "📅 Smenalar",
            "analytics": "📊 Analitika",
            "broadcast": "📢 Xabar yuborish",
            "config": "⚙️ Sozlamalar",
            "logs": "📝 Loglar",
            "back": "◀️ Orqaga",
        },
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = ReplyKeyboardBuilder()

    # Admin actions
    builder.add(KeyboardButton(text=lang_texts["users"]))
    builder.add(KeyboardButton(text=lang_texts["requests"]))
    builder.add(KeyboardButton(text=lang_texts["shifts"]))
    builder.add(KeyboardButton(text=lang_texts["analytics"]))
    builder.add(KeyboardButton(text=lang_texts["broadcast"]))
    builder.add(KeyboardButton(text=lang_texts["config"]))
    builder.add(KeyboardButton(text=lang_texts["logs"]))
    builder.add(KeyboardButton(text=lang_texts["back"]))

    builder.adjust(2, 2, 2, 2)  # 2-2-2-2 layout
    return builder.as_markup(resize_keyboard=True)


# ===========================================
# User Management
# ===========================================


def get_user_search_options_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Get user search options keyboard.

    Args:
        language: Language code

    Returns:
        Inline keyboard with search options
    """
    texts = {
        "ru": {
            "by_phone": "📱 По телефону",
            "by_name": "👤 По имени",
            "by_role": "🏷 По роли",
            "all_users": "📋 Все пользователи",
            "active_only": "✅ Только активные",
            "blocked_only": "🚫 Только заблокированные",
        },
        "uz": {
            "by_phone": "📱 Telefon bo'yicha",
            "by_name": "👤 Ism bo'yicha",
            "by_role": "🏷 Rol bo'yicha",
            "all_users": "📋 Barcha foydalanuvchilar",
            "active_only": "✅ Faqat faol",
            "blocked_only": "🚫 Faqat bloklangan",
        },
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    builder.add(InlineKeyboardButton(text=lang_texts["by_phone"], callback_data="user_search:phone"))
    builder.add(InlineKeyboardButton(text=lang_texts["by_name"], callback_data="user_search:name"))
    builder.add(InlineKeyboardButton(text=lang_texts["by_role"], callback_data="user_search:role"))
    builder.add(InlineKeyboardButton(text=lang_texts["all_users"], callback_data="user_search:all"))
    builder.add(
        InlineKeyboardButton(text=lang_texts["active_only"], callback_data="user_search:active")
    )
    builder.add(
        InlineKeyboardButton(text=lang_texts["blocked_only"], callback_data="user_search:blocked")
    )

    builder.adjust(2, 2, 2)
    return builder.as_markup()


def get_user_actions_keyboard(
    user_id: str, is_active: bool, language: str = "ru"
) -> InlineKeyboardMarkup:
    """
    Get actions keyboard for specific user.

    Args:
        user_id: User UUID
        is_active: Whether user is active
        language: Language code

    Returns:
        Inline keyboard with user actions
    """
    texts = {
        "ru": {
            "view": "👁 Просмотр",
            "edit_role": "🏷 Изменить роль",
            "block": "🚫 Заблокировать",
            "unblock": "✅ Разблокировать",
            "requests": "📋 Заявки",
            "shifts": "📅 Смены",
            "reset_password": "🔑 Сбросить пароль",
            "delete": "🗑 Удалить",
        },
        "uz": {
            "view": "👁 Ko'rish",
            "edit_role": "🏷 Rolni o'zgartirish",
            "block": "🚫 Bloklash",
            "unblock": "✅ Blokdan chiqarish",
            "requests": "📋 Arizalar",
            "shifts": "📅 Smenalar",
            "reset_password": "🔑 Parolni tiklash",
            "delete": "🗑 O'chirish",
        },
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    # View user details
    builder.add(InlineKeyboardButton(text=lang_texts["view"], callback_data=f"user:view:{user_id}"))

    # Edit role
    builder.add(
        InlineKeyboardButton(text=lang_texts["edit_role"], callback_data=f"user:role:{user_id}")
    )

    # Block/Unblock
    if is_active:
        builder.add(
            InlineKeyboardButton(text=lang_texts["block"], callback_data=f"user:block:{user_id}")
        )
    else:
        builder.add(
            InlineKeyboardButton(text=lang_texts["unblock"], callback_data=f"user:unblock:{user_id}")
        )

    # View user's requests
    builder.add(
        InlineKeyboardButton(text=lang_texts["requests"], callback_data=f"user:requests:{user_id}")
    )

    # View user's shifts
    builder.add(
        InlineKeyboardButton(text=lang_texts["shifts"], callback_data=f"user:shifts:{user_id}")
    )

    # Reset password
    builder.add(
        InlineKeyboardButton(
            text=lang_texts["reset_password"], callback_data=f"user:reset_pwd:{user_id}"
        )
    )

    # Delete user (dangerous)
    builder.add(
        InlineKeyboardButton(text=lang_texts["delete"], callback_data=f"user:delete:{user_id}")
    )

    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def get_role_selection_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Get role selection keyboard.

    Args:
        language: Language code

    Returns:
        Inline keyboard with role options
    """
    texts = {
        "ru": {
            "applicant": "👤 Заявитель",
            "executor": "🔧 Исполнитель",
            "manager": "👔 Менеджер",
            "admin": "👨‍💼 Администратор",
        },
        "uz": {
            "applicant": "👤 Ariza beruvchi",
            "executor": "🔧 Ijrochi",
            "manager": "👔 Menejer",
            "admin": "👨‍💼 Administrator",
        },
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    builder.add(InlineKeyboardButton(text=lang_texts["applicant"], callback_data="role:applicant"))
    builder.add(InlineKeyboardButton(text=lang_texts["executor"], callback_data="role:executor"))
    builder.add(InlineKeyboardButton(text=lang_texts["manager"], callback_data="role:manager"))
    builder.add(InlineKeyboardButton(text=lang_texts["admin"], callback_data="role:admin"))

    builder.adjust(2, 2)
    return builder.as_markup()


# ===========================================
# Request Management (Admin)
# ===========================================


def get_request_search_options_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Get request search options keyboard.

    Args:
        language: Language code

    Returns:
        Inline keyboard with search options
    """
    texts = {
        "ru": {
            "by_number": "🔢 По номеру",
            "by_status": "📊 По статусу",
            "by_executor": "🔧 По исполнителю",
            "by_building": "🏢 По дому",
            "by_date": "📅 По дате",
            "all_requests": "📋 Все заявки",
        },
        "uz": {
            "by_number": "🔢 Raqam bo'yicha",
            "by_status": "📊 Holat bo'yicha",
            "by_executor": "🔧 Ijrochi bo'yicha",
            "by_building": "🏢 Bino bo'yicha",
            "by_date": "📅 Sana bo'yicha",
            "all_requests": "📋 Barcha arizalar",
        },
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    builder.add(
        InlineKeyboardButton(text=lang_texts["by_number"], callback_data="req_search:number")
    )
    builder.add(
        InlineKeyboardButton(text=lang_texts["by_status"], callback_data="req_search:status")
    )
    builder.add(
        InlineKeyboardButton(text=lang_texts["by_executor"], callback_data="req_search:executor")
    )
    builder.add(
        InlineKeyboardButton(text=lang_texts["by_building"], callback_data="req_search:building")
    )
    builder.add(InlineKeyboardButton(text=lang_texts["by_date"], callback_data="req_search:date"))
    builder.add(InlineKeyboardButton(text=lang_texts["all_requests"], callback_data="req_search:all"))

    builder.adjust(2, 2, 2)
    return builder.as_markup()


def get_request_admin_actions_keyboard(
    request_number: str, status: str, language: str = "ru"
) -> InlineKeyboardMarkup:
    """
    Get admin actions keyboard for specific request.

    Args:
        request_number: Request number
        status: Current request status
        language: Language code

    Returns:
        Inline keyboard with admin actions
    """
    texts = {
        "ru": {
            "view": "👁 Просмотр",
            "reassign": "🔄 Переназначить",
            "change_priority": "⚡ Изменить приоритет",
            "change_status": "📊 Изменить статус",
            "cancel": "❌ Отменить",
            "history": "📜 История",
            "comments": "💬 Комментарии",
        },
        "uz": {
            "view": "👁 Ko'rish",
            "reassign": "🔄 Qayta tayinlash",
            "change_priority": "⚡ Ustuvorlikni o'zgartirish",
            "change_status": "📊 Holatni o'zgartirish",
            "cancel": "❌ Bekor qilish",
            "history": "📜 Tarix",
            "comments": "💬 Izohlar",
        },
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    # View details
    builder.add(
        InlineKeyboardButton(text=lang_texts["view"], callback_data=f"req:view:{request_number}")
    )

    # Reassign executor
    builder.add(
        InlineKeyboardButton(
            text=lang_texts["reassign"], callback_data=f"req:reassign:{request_number}"
        )
    )

    # Change priority
    builder.add(
        InlineKeyboardButton(
            text=lang_texts["change_priority"], callback_data=f"req:priority:{request_number}"
        )
    )

    # Change status
    builder.add(
        InlineKeyboardButton(
            text=lang_texts["change_status"], callback_data=f"req:status:{request_number}"
        )
    )

    # Cancel request
    if status not in ["cancelled", "completed"]:
        builder.add(
            InlineKeyboardButton(
                text=lang_texts["cancel"], callback_data=f"req:cancel:{request_number}"
            )
        )

    # View history
    builder.add(
        InlineKeyboardButton(
            text=lang_texts["history"], callback_data=f"req:history:{request_number}"
        )
    )

    # View comments
    builder.add(
        InlineKeyboardButton(
            text=lang_texts["comments"], callback_data=f"req:comments:{request_number}"
        )
    )

    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def get_priority_selection_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Get priority selection keyboard.

    Args:
        language: Language code

    Returns:
        Inline keyboard with priority options
    """
    texts = {
        "ru": {
            "low": "🟢 Низкий",
            "normal": "🟡 Средний",
            "high": "🟠 Высокий",
            "urgent": "🔴 Срочный",
        },
        "uz": {
            "low": "🟢 Past",
            "normal": "🟡 O'rta",
            "high": "🟠 Yuqori",
            "urgent": "🔴 Shoshilinch",
        },
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    builder.add(InlineKeyboardButton(text=lang_texts["low"], callback_data="priority:low"))
    builder.add(InlineKeyboardButton(text=lang_texts["normal"], callback_data="priority:normal"))
    builder.add(InlineKeyboardButton(text=lang_texts["high"], callback_data="priority:high"))
    builder.add(InlineKeyboardButton(text=lang_texts["urgent"], callback_data="priority:urgent"))

    builder.adjust(2, 2)
    return builder.as_markup()


def get_status_selection_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Get status selection keyboard.

    Args:
        language: Language code

    Returns:
        Inline keyboard with status options
    """
    texts = {
        "ru": {
            "new": "🆕 Новая",
            "assigned": "👤 Назначена",
            "in_progress": "⚙️ В работе",
            "completed": "✅ Выполнена",
            "cancelled": "❌ Отменена",
        },
        "uz": {
            "new": "🆕 Yangi",
            "assigned": "👤 Tayinlangan",
            "in_progress": "⚙️ Jarayonda",
            "completed": "✅ Bajarildi",
            "cancelled": "❌ Bekor qilindi",
        },
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    builder.add(InlineKeyboardButton(text=lang_texts["new"], callback_data="status:new"))
    builder.add(InlineKeyboardButton(text=lang_texts["assigned"], callback_data="status:assigned"))
    builder.add(
        InlineKeyboardButton(text=lang_texts["in_progress"], callback_data="status:in_progress")
    )
    builder.add(InlineKeyboardButton(text=lang_texts["completed"], callback_data="status:completed"))
    builder.add(InlineKeyboardButton(text=lang_texts["cancelled"], callback_data="status:cancelled"))

    builder.adjust(2, 2, 1)
    return builder.as_markup()


# ===========================================
# Broadcast Messages
# ===========================================


def get_broadcast_target_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Get broadcast target selection keyboard.

    Args:
        language: Language code

    Returns:
        Inline keyboard with target options
    """
    texts = {
        "ru": {
            "all": "📢 Всем пользователям",
            "applicants": "👤 Заявителям",
            "executors": "🔧 Исполнителям",
            "managers": "👔 Менеджерам",
            "admins": "👨‍💼 Администраторам",
            "custom": "🎯 Выборочно",
        },
        "uz": {
            "all": "📢 Barcha foydalanuvchilarga",
            "applicants": "👤 Ariza beruvchilarga",
            "executors": "🔧 Ijrochilarga",
            "managers": "👔 Menejerlarga",
            "admins": "👨‍💼 Administratorlarga",
            "custom": "🎯 Tanlab",
        },
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    builder.add(InlineKeyboardButton(text=lang_texts["all"], callback_data="broadcast:all"))
    builder.add(
        InlineKeyboardButton(text=lang_texts["applicants"], callback_data="broadcast:applicants")
    )
    builder.add(
        InlineKeyboardButton(text=lang_texts["executors"], callback_data="broadcast:executors")
    )
    builder.add(
        InlineKeyboardButton(text=lang_texts["managers"], callback_data="broadcast:managers")
    )
    builder.add(InlineKeyboardButton(text=lang_texts["admins"], callback_data="broadcast:admins"))
    builder.add(InlineKeyboardButton(text=lang_texts["custom"], callback_data="broadcast:custom"))

    builder.adjust(1)
    return builder.as_markup()


def get_broadcast_schedule_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Get broadcast schedule keyboard.

    Args:
        language: Language code

    Returns:
        Inline keyboard with schedule options
    """
    texts = {
        "ru": {
            "immediate": "⚡ Отправить сейчас",
            "scheduled": "⏰ Запланировать",
        },
        "uz": {
            "immediate": "⚡ Hozir yuborish",
            "scheduled": "⏰ Rejalashtirish",
        },
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    builder.add(
        InlineKeyboardButton(text=lang_texts["immediate"], callback_data="schedule:immediate")
    )
    builder.add(
        InlineKeyboardButton(text=lang_texts["scheduled"], callback_data="schedule:scheduled")
    )

    builder.adjust(1)
    return builder.as_markup()


# ===========================================
# System Configuration
# ===========================================


def get_config_categories_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Get system configuration categories keyboard.

    Args:
        language: Language code

    Returns:
        Inline keyboard with config categories
    """
    texts = {
        "ru": {
            "rate_limits": "⏱ Лимиты запросов",
            "notifications": "🔔 Уведомления",
            "assignments": "📋 Назначения",
            "shifts": "📅 Смены",
            "general": "⚙️ Общие настройки",
        },
        "uz": {
            "rate_limits": "⏱ So'rovlar limiti",
            "notifications": "🔔 Bildirishnomalar",
            "assignments": "📋 Tayinlashlar",
            "shifts": "📅 Smenalar",
            "general": "⚙️ Umumiy sozlamalar",
        },
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    builder.add(
        InlineKeyboardButton(text=lang_texts["rate_limits"], callback_data="config:rate_limits")
    )
    builder.add(
        InlineKeyboardButton(text=lang_texts["notifications"], callback_data="config:notifications")
    )
    builder.add(
        InlineKeyboardButton(text=lang_texts["assignments"], callback_data="config:assignments")
    )
    builder.add(InlineKeyboardButton(text=lang_texts["shifts"], callback_data="config:shifts"))
    builder.add(InlineKeyboardButton(text=lang_texts["general"], callback_data="config:general"))

    builder.adjust(1)
    return builder.as_markup()


# ===========================================
# Analytics
# ===========================================


def get_analytics_reports_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Get analytics reports selection keyboard.

    Args:
        language: Language code

    Returns:
        Inline keyboard with report types
    """
    texts = {
        "ru": {
            "requests": "📋 Заявки",
            "users": "👥 Пользователи",
            "shifts": "📅 Смены",
            "executors": "🔧 Исполнители",
            "buildings": "🏢 Объекты",
            "overall": "📊 Общая статистика",
        },
        "uz": {
            "requests": "📋 Arizalar",
            "users": "👥 Foydalanuvchilar",
            "shifts": "📅 Smenalar",
            "executors": "🔧 Ijrochilar",
            "buildings": "🏢 Obyektlar",
            "overall": "📊 Umumiy statistika",
        },
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    builder.add(
        InlineKeyboardButton(text=lang_texts["requests"], callback_data="analytics:requests")
    )
    builder.add(InlineKeyboardButton(text=lang_texts["users"], callback_data="analytics:users"))
    builder.add(InlineKeyboardButton(text=lang_texts["shifts"], callback_data="analytics:shifts"))
    builder.add(
        InlineKeyboardButton(text=lang_texts["executors"], callback_data="analytics:executors")
    )
    builder.add(
        InlineKeyboardButton(text=lang_texts["buildings"], callback_data="analytics:buildings")
    )
    builder.add(
        InlineKeyboardButton(text=lang_texts["overall"], callback_data="analytics:overall")
    )

    builder.adjust(2, 2, 2)
    return builder.as_markup()


# ===========================================
# Confirmation Keyboards
# ===========================================


def get_admin_confirmation_keyboard(
    action: str, item_id: str, language: str = "ru"
) -> InlineKeyboardMarkup:
    """
    Get admin confirmation keyboard.

    Args:
        action: Action type (delete, block, broadcast, etc.)
        item_id: Item identifier
        language: Language code

    Returns:
        Inline keyboard with confirm/cancel
    """
    texts = {
        "ru": {
            "confirm": "✅ Подтвердить",
            "cancel": "❌ Отмена",
        },
        "uz": {
            "confirm": "✅ Tasdiqlash",
            "cancel": "❌ Bekor qilish",
        },
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    builder.add(
        InlineKeyboardButton(
            text=lang_texts["confirm"], callback_data=f"admin:{action}:confirm:{item_id}"
        )
    )
    builder.add(
        InlineKeyboardButton(
            text=lang_texts["cancel"], callback_data=f"admin:{action}:cancel:{item_id}"
        )
    )

    builder.adjust(1)
    return builder.as_markup()
