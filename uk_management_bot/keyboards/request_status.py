"""
Клавиатуры для управления статусами заявок
Создает интерактивные клавиатуры для изменения статусов заявок
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List

from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.constants import (
    REQUEST_STATUS_IN_PROGRESS, REQUEST_STATUS_PURCHASE,
    REQUEST_STATUS_CLARIFICATION, REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_APPROVED
)
from uk_management_bot.utils.request_helpers import RequestCallbackHelper

def get_status_selection_keyboard(available_statuses: List[str], language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура выбора нового статуса заявки
    
    Args:
        available_statuses: Список доступных статусов
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопками статусов
    """
    keyboard = []
    
    # Маппинг статусов на отображаемые названия
    status_display_names = {
        REQUEST_STATUS_IN_PROGRESS: "🔄 В работу",
        REQUEST_STATUS_PURCHASE: "🛒 Закупка материалов",
        REQUEST_STATUS_CLARIFICATION: "❓ Уточнение",
        REQUEST_STATUS_COMPLETED: "✅ Исполнено",
        REQUEST_STATUS_APPROVED: "👍 Принято"
    }
    
    for status in available_statuses:
        display_name = status_display_names.get(status, status)
        keyboard.append([
            InlineKeyboardButton(
                text=display_name,
                callback_data=f"status_{status}"
            )
        ])
    
    # Добавляем кнопку отмены
    keyboard.append([
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="cancel_status_change"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_status_confirmation_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура подтверждения изменения статуса
    
    Args:
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопками подтверждения
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data="confirm_status_change"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="cancel_status_change"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_executor_status_actions_keyboard(request_number: str, current_status: str, language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура действий исполнителя с заявкой
    
    Args:
        request_number: Номер заявки
        current_status: Текущий статус заявки
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с действиями исполнителя
    """
    keyboard = []
    
    # Действия в зависимости от статуса
    if current_status == REQUEST_STATUS_IN_PROGRESS:
        keyboard.extend([
            [
                InlineKeyboardButton(
                    text="🛒 Закупка материалов",
                    callback_data=RequestCallbackHelper.create_callback_data_with_request_number("purchase_materials_", request_number)
                )
            ],
            [
                InlineKeyboardButton(
                    text="❓ Запросить уточнение",
                    callback_data=RequestCallbackHelper.create_callback_data_with_request_number("request_clarification_", request_number)
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Завершить работу",
                    callback_data=RequestCallbackHelper.create_callback_data_with_request_number("complete_work_", request_number)
                )
            ]
        ])
    elif current_status == REQUEST_STATUS_PURCHASE:
        keyboard.append([
            InlineKeyboardButton(
                text="🔄 Вернуть в работу",
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("return_to_work_", request_number)
            )
        ])
    elif current_status == REQUEST_STATUS_COMPLETED:
        keyboard.append([
            InlineKeyboardButton(
                text="📋 Просмотр отчета",
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("view_report_", request_number)
            )
        ])
    
    # Общие действия
    keyboard.extend([
        [
            InlineKeyboardButton(
                text="📝 Добавить комментарий",
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("add_comment_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Просмотр комментариев",
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("view_comments_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Назад к заявкам",
                callback_data="back_to_requests"
            )
        ]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_manager_status_actions_keyboard(request_number: str, current_status: str, language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура действий менеджера с заявкой
    
    Args:
        request_number: Номер заявки
        current_status: Текущий статус заявки
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с действиями менеджера
    """
    keyboard = []
    
    # Действия в зависимости от статуса
    if current_status == "Новая":
        keyboard.extend([
            [
                InlineKeyboardButton(
                    text="📋 Назначить заявку",
                    callback_data=RequestCallbackHelper.create_callback_data_with_request_number("assign_request_", request_number)
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Взять в работу",
                    callback_data=f"status_{REQUEST_STATUS_IN_PROGRESS}"
                )
            ]
        ])
    elif current_status == REQUEST_STATUS_IN_PROGRESS:
        keyboard.extend([
            [
                InlineKeyboardButton(
                    text="❓ Запросить уточнение",
                    callback_data=f"status_{REQUEST_STATUS_CLARIFICATION}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Завершить работу",
                    callback_data=f"status_{REQUEST_STATUS_COMPLETED}"
                )
            ]
        ])
    elif current_status == REQUEST_STATUS_PURCHASE:
        keyboard.append([
            InlineKeyboardButton(
                text="🔄 Вернуть в работу",
                callback_data=f"status_{REQUEST_STATUS_IN_PROGRESS}"
            )
        ])
    elif current_status == REQUEST_STATUS_CLARIFICATION:
        keyboard.append([
            InlineKeyboardButton(
                text="🔄 Вернуть в работу",
                callback_data=f"status_{REQUEST_STATUS_IN_PROGRESS}"
            )
        ])
    elif current_status == REQUEST_STATUS_COMPLETED:
        keyboard.append([
            InlineKeyboardButton(
                text="👍 Принять работу",
                callback_data=f"status_{REQUEST_STATUS_APPROVED}"
            )
        ])
    
    # Общие действия
    keyboard.extend([
        [
            InlineKeyboardButton(
                text="📝 Добавить комментарий",
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("add_comment_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text="📋 Просмотр комментариев",
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("view_comments_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text="👥 Просмотр назначений",
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("view_assignments_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Назад к заявкам",
                callback_data="back_to_requests"
            )
        ]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_applicant_status_actions_keyboard(request_number: str, current_status: str, language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура действий заявителя с заявкой
    
    Args:
        request_number: Номер заявки
        current_status: Текущий статус заявки
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с действиями заявителя
    """
    keyboard = []
    
    # Действия в зависимости от статуса
    if current_status == REQUEST_STATUS_COMPLETED:
        keyboard.append([
            InlineKeyboardButton(
                text="👍 Принять работу",
                callback_data=f"status_{REQUEST_STATUS_APPROVED}"
            )
        ])
    
    # Общие действия
    keyboard.extend([
        [
            InlineKeyboardButton(
                text="📋 Просмотр комментариев",
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("view_comments_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text="📊 Просмотр отчета",
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("view_report_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 Назад к заявкам",
                callback_data="back_to_requests"
            )
        ]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_quick_status_actions_keyboard(request_number: str, language: str = "ru") -> InlineKeyboardMarkup:
    """
    Быстрые действия со статусом заявки
    
    Args:
        request_number: Номер заявки
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с быстрыми действиями
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text="🔄 В работу",
                callback_data=f"quick_status_{REQUEST_STATUS_IN_PROGRESS}_{request_number}"
            ),
            InlineKeyboardButton(
                text="❓ Уточнение",
                callback_data=f"quick_status_{REQUEST_STATUS_CLARIFICATION}_{request_number}"
            )
        ],
        [
            InlineKeyboardButton(
                text="✅ Исполнено",
                callback_data=f"quick_status_{REQUEST_STATUS_COMPLETED}_{request_number}"
            ),
            InlineKeyboardButton(
                text="👍 Принято",
                callback_data=f"quick_status_{REQUEST_STATUS_APPROVED}_{request_number}"
            )
        ],
        [
            InlineKeyboardButton(
                text="📝 Комментарий",
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("add_comment_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="cancel_status_change"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
