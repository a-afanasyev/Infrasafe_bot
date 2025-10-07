"""
Common Keyboards
UK Management Bot - Bot Gateway Service

Reusable keyboard builders for common bot interactions.
"""

from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


def get_main_menu_keyboard(role: str, language: str = "ru") -> ReplyKeyboardMarkup:
    """
    Get main menu keyboard based on user role.

    Args:
        role: User role (applicant, executor, manager, admin)
        language: Language code (ru, uz)

    Returns:
        Reply keyboard with main menu buttons
    """
    builder = ReplyKeyboardBuilder()

    # Text labels based on language
    texts = {
        "ru": {
            "my_requests": "📋 Мои заявки",
            "create_request": "➕ Создать заявку",
            "my_shifts": "📅 Мои смены",
            "admin_panel": "👨‍💼 Админ-панель",
            "help": "❓ Помощь",
            "settings": "⚙️ Настройки",
            "analytics": "📊 Аналитика",
            "users": "👥 Пользователи",
        },
        "uz": {
            "my_requests": "📋 Mening arizalarim",
            "create_request": "➕ Ariza yaratish",
            "my_shifts": "📅 Mening smenalarim",
            "admin_panel": "👨‍💼 Admin panel",
            "help": "❓ Yordam",
            "settings": "⚙️ Sozlamalar",
            "analytics": "📊 Analitika",
            "users": "👥 Foydalanuvchilar",
        }
    }

    lang_texts = texts.get(language, texts["ru"])

    # Common buttons for all roles
    builder.add(KeyboardButton(text=lang_texts["my_requests"]))

    # Applicant buttons
    if role in ["applicant", "executor", "manager", "admin"]:
        builder.add(KeyboardButton(text=lang_texts["create_request"]))

    # Executor buttons
    if role in ["executor", "manager", "admin"]:
        builder.add(KeyboardButton(text=lang_texts["my_shifts"]))

    # Manager/Admin buttons
    if role in ["manager", "admin"]:
        builder.add(KeyboardButton(text=lang_texts["admin_panel"]))

    # Always show help and settings
    builder.add(KeyboardButton(text=lang_texts["help"]))
    builder.add(KeyboardButton(text=lang_texts["settings"]))

    # 2 buttons per row
    builder.adjust(2)

    return builder.as_markup(resize_keyboard=True)


def get_language_keyboard() -> InlineKeyboardMarkup:
    """
    Get language selection keyboard.

    Returns:
        Inline keyboard with language options
    """
    builder = InlineKeyboardBuilder()

    builder.add(
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
        InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang:uz")
    )

    builder.adjust(2)
    return builder.as_markup()


def get_back_button(callback_data: str = "back", language: str = "ru") -> InlineKeyboardMarkup:
    """
    Get back button inline keyboard.

    Args:
        callback_data: Callback data for back button
        language: Language code

    Returns:
        Inline keyboard with back button
    """
    text = "◀️ Назад" if language == "ru" else "◀️ Orqaga"

    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=text, callback_data=callback_data))

    return builder.as_markup()


def get_cancel_keyboard(language: str = "ru") -> ReplyKeyboardMarkup:
    """
    Get cancel keyboard for FSM states.

    Args:
        language: Language code

    Returns:
        Reply keyboard with cancel button
    """
    text = "❌ Отмена" if language == "ru" else "❌ Bekor qilish"

    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text=text))

    return builder.as_markup(resize_keyboard=True)


def get_confirmation_keyboard(
    confirm_callback: str,
    cancel_callback: str,
    language: str = "ru"
) -> InlineKeyboardMarkup:
    """
    Get confirmation inline keyboard (Yes/No).

    Args:
        confirm_callback: Callback data for confirm button
        cancel_callback: Callback data for cancel button
        language: Language code

    Returns:
        Inline keyboard with confirmation buttons
    """
    texts = {
        "ru": {"yes": "✅ Да", "no": "❌ Нет"},
        "uz": {"yes": "✅ Ha", "no": "❌ Yo'q"}
    }

    lang_texts = texts.get(language, texts["ru"])

    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text=lang_texts["yes"], callback_data=confirm_callback),
        InlineKeyboardButton(text=lang_texts["no"], callback_data=cancel_callback)
    )

    builder.adjust(2)
    return builder.as_markup()


def get_pagination_keyboard(
    current_page: int,
    total_pages: int,
    callback_prefix: str
) -> InlineKeyboardMarkup:
    """
    Get pagination keyboard.

    Args:
        current_page: Current page number (1-indexed)
        total_pages: Total number of pages
        callback_prefix: Prefix for callback data (e.g., "requests_page")

    Returns:
        Inline keyboard with pagination buttons
    """
    builder = InlineKeyboardBuilder()

    # Previous page button
    if current_page > 1:
        builder.add(
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data=f"{callback_prefix}:{current_page - 1}"
            )
        )

    # Page indicator
    builder.add(
        InlineKeyboardButton(
            text=f"📄 {current_page}/{total_pages}",
            callback_data="noop"
        )
    )

    # Next page button
    if current_page < total_pages:
        builder.add(
            InlineKeyboardButton(
                text="Вперед ▶️",
                callback_data=f"{callback_prefix}:{current_page + 1}"
            )
        )

    builder.adjust(3)
    return builder.as_markup()
