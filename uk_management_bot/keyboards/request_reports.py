"""
Клавиатуры для управления отчетами о выполнении заявок
Создает интерактивные клавиатуры для принятия и доработки заявок
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.constants import REQUEST_STATUS_APPROVED

def get_report_confirmation_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура подтверждения принятия заявки
    
    Args:
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопками подтверждения
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text="✅ Принять заявку",
                callback_data="confirm_approval"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="cancel_approval"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_report_actions_keyboard(request_number: str, current_status: str, language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура действий с отчетом

    Args:
        request_number: Номер заявки
        current_status: Текущий статус заявки
        language: Язык интерфейса

    Returns:
        InlineKeyboardMarkup: Клавиатура с действиями
    """
    keyboard = []
    
    # Действия в зависимости от статуса
    if current_status == "Исполнено":
        keyboard.extend([
            [
                InlineKeyboardButton(
                    text="👍 Принять заявку",
                    callback_data=f"approve_request_{request_number}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔧 Запросить доработку",
                    callback_data=f"request_revision_{request_number}"
                )
            ]
        ])
    elif current_status == REQUEST_STATUS_APPROVED:
        keyboard.append([
            InlineKeyboardButton(
                text="✅ Заявка принята",
                callback_data="request_already_approved"
            )
        ])
    
    # Общие действия
    keyboard.extend([
        [
            InlineKeyboardButton(
                text="📝 Добавить комментарий",
                callback_data=f"add_comment_{request_number}"
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Просмотр комментариев",
                callback_data=f"view_comments_{request_number}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Назад к заявке",
                callback_data=f"view_request_{request_number}"
            )
        ]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_report_details_keyboard(request_number: int, language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура детального просмотра отчета
    
    Args:
        request_number: ID заявки
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с действиями
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text="📊 Полный отчет",
                callback_data=f"view_full_report_{request_number}"
            )
        ],
        [
            InlineKeyboardButton(
                text="📝 История изменений",
                callback_data=f"view_request_history_{request_number}"
            )
        ],
        [
            InlineKeyboardButton(
                text="👥 Назначения",
                callback_data=f"view_assignments_{request_number}"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Назад к отчету",
                callback_data=f"back_to_report_{request_number}"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
