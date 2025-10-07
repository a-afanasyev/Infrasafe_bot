"""
Request Keyboards
UK Management Bot - Bot Gateway Service

Keyboard builders for request management.
"""

from typing import List, Dict, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_request_actions_keyboard(
    request_number: str,
    status: str,
    user_role: str,
    language: str = "ru"
) -> InlineKeyboardMarkup:
    """
    Get request actions keyboard based on status and user role.

    Args:
        request_number: Request number
        status: Request status
        user_role: User role (applicant, executor, manager, admin)
        language: Language code

    Returns:
        Inline keyboard with available actions
    """
    texts = {
        "ru": {
            "view": "👁 Просмотр",
            "comment": "💬 Комментарий",
            "take": "✋ Взять в работу",
            "complete": "✅ Завершить",
            "cancel": "❌ Отменить",
            "reassign": "👤 Переназначить",
            "back": "◀️ Назад"
        },
        "uz": {
            "view": "👁 Ko'rish",
            "comment": "💬 Izoh",
            "take": "✋ Ishga olish",
            "complete": "✅ Yakunlash",
            "cancel": "❌ Bekor qilish",
            "reassign": "👤 Qayta tayinlash",
            "back": "◀️ Orqaga"
        }
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    # View details (always available)
    builder.add(
        InlineKeyboardButton(
            text=lang_texts["view"],
            callback_data=f"request:view:{request_number}"
        )
    )

    # Add comment (always available)
    builder.add(
        InlineKeyboardButton(
            text=lang_texts["comment"],
            callback_data=f"request:comment:{request_number}"
        )
    )

    # Role-specific actions
    if status == "new":
        # Executor can take request
        if user_role in ["executor", "manager", "admin"]:
            builder.add(
                InlineKeyboardButton(
                    text=lang_texts["take"],
                    callback_data=f"request:take:{request_number}"
                )
            )

    elif status == "in_progress":
        # Executor can complete request
        if user_role in ["executor", "manager", "admin"]:
            builder.add(
                InlineKeyboardButton(
                    text=lang_texts["complete"],
                    callback_data=f"request:complete:{request_number}"
                )
            )

        # Manager/Admin can reassign
        if user_role in ["manager", "admin"]:
            builder.add(
                InlineKeyboardButton(
                    text=lang_texts["reassign"],
                    callback_data=f"request:reassign:{request_number}"
                )
            )

    # Cancel request (applicant, manager, admin)
    if status not in ["completed", "cancelled"] and user_role in ["applicant", "manager", "admin"]:
        builder.add(
            InlineKeyboardButton(
                text=lang_texts["cancel"],
                callback_data=f"request:cancel:{request_number}"
            )
        )

    # Back button
    builder.add(
        InlineKeyboardButton(
            text=lang_texts["back"],
            callback_data="requests:list"
        )
    )

    builder.adjust(2)
    return builder.as_markup()


def get_request_list_keyboard(
    requests: List[Dict[str, Any]],
    language: str = "ru"
) -> InlineKeyboardMarkup:
    """
    Get request list keyboard.

    Args:
        requests: List of request dicts
        language: Language code

    Returns:
        Inline keyboard with request list
    """
    builder = InlineKeyboardBuilder()

    for request in requests:
        request_number = request.get("request_number")
        status = request.get("status")
        building = request.get("building_name", "?")
        apartment = request.get("apartment", "?")

        # Status emoji
        status_emoji = {
            "new": "🆕",
            "in_progress": "⏳",
            "completed": "✅",
            "cancelled": "❌"
        }.get(status, "📋")

        text = f"{status_emoji} {request_number} | {building}, кв. {apartment}"

        builder.add(
            InlineKeyboardButton(
                text=text,
                callback_data=f"request:view:{request_number}"
            )
        )

    builder.adjust(1)
    return builder.as_markup()


def get_request_status_filter_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Get request status filter keyboard.

    Args:
        language: Language code

    Returns:
        Inline keyboard with status filters
    """
    texts = {
        "ru": {
            "all": "📋 Все",
            "new": "🆕 Новые",
            "in_progress": "⏳ В работе",
            "completed": "✅ Завершённые",
            "cancelled": "❌ Отменённые"
        },
        "uz": {
            "all": "📋 Hammasi",
            "new": "🆕 Yangi",
            "in_progress": "⏳ Jarayonda",
            "completed": "✅ Yakunlangan",
            "cancelled": "❌ Bekor qilingan"
        }
    }

    lang_texts = texts.get(language, texts["ru"])
    builder = InlineKeyboardBuilder()

    for status_key, text in lang_texts.items():
        callback_data = f"requests:filter:{status_key}" if status_key != "all" else "requests:filter:all"
        builder.add(InlineKeyboardButton(text=text, callback_data=callback_data))

    builder.adjust(2)
    return builder.as_markup()


def get_executor_selection_keyboard(
    executors: List[Dict[str, Any]],
    request_number: str
) -> InlineKeyboardMarkup:
    """
    Get executor selection keyboard.

    Args:
        executors: List of executor dicts
        request_number: Request number

    Returns:
        Inline keyboard with executor list
    """
    builder = InlineKeyboardBuilder()

    for executor in executors:
        user_id = executor.get("id")
        first_name = executor.get("first_name", "")
        last_name = executor.get("last_name", "")
        specialization = executor.get("specialization", "")

        text = f"👤 {first_name} {last_name}"
        if specialization:
            text += f" ({specialization})"

        builder.add(
            InlineKeyboardButton(
                text=text,
                callback_data=f"request:assign:{request_number}:{user_id}"
            )
        )

    builder.adjust(1)
    return builder.as_markup()
