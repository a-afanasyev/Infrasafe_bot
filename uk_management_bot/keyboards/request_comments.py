"""
Клавиатуры для управления комментариями к заявкам
Создает интерактивные клавиатуры для добавления и просмотра комментариев
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.constants import (
    COMMENT_TYPE_CLARIFICATION, COMMENT_TYPE_PURCHASE, COMMENT_TYPE_REPORT
)
from uk_management_bot.utils.request_helpers import RequestCallbackHelper

def get_comment_type_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура выбора типа комментария
    
    Args:
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с типами комментариев
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text="❓ Уточнение",
                callback_data=f"comment_type_{COMMENT_TYPE_CLARIFICATION}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🛒 Закупка материалов",
                callback_data=f"comment_type_{COMMENT_TYPE_PURCHASE}"
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Отчет о выполнении",
                callback_data=f"comment_type_{COMMENT_TYPE_REPORT}"
            )
        ],
        [
            InlineKeyboardButton(
                text="💬 Общий комментарий",
                callback_data="comment_type_general"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="cancel_comment"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_comment_confirmation_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура подтверждения добавления комментария
    
    Args:
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопками подтверждения
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text="✅ Добавить комментарий",
                callback_data="confirm_comment"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="cancel_comment"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_comments_list_keyboard(request_number: str, language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура для списка комментариев
    
    Args:
        request_number: Номер заявки
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с действиями для комментариев
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text="❓ Только уточнения",
                callback_data=f"view_comments_by_type_{COMMENT_TYPE_CLARIFICATION}_{request_number}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🛒 Только закупки",
                callback_data=f"view_comments_by_type_{COMMENT_TYPE_PURCHASE}_{request_number}"
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Только отчеты",
                callback_data=f"view_comments_by_type_{COMMENT_TYPE_REPORT}_{request_number}"
            )
        ],
        [
            InlineKeyboardButton(
                text="📝 Добавить комментарий",
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("add_comment_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Назад к заявке",
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("view_request_", request_number)
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_comment_actions_keyboard(request_number: str, comment_id: int, language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура действий с комментарием
    
    Args:
        request_number: Номер заявки
        comment_id: ID комментария
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с действиями
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text="📝 Ответить на комментарий",
                callback_data=f"reply_to_comment_{comment_id}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Назад к комментариям",
                callback_data=f"back_to_comments_{request_number}"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
