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
        REQUEST_STATUS_IN_PROGRESS: get_text("request_status.keyboards.status_in_progress", language=language),
        REQUEST_STATUS_PURCHASE: get_text("request_status.keyboards.status_purchase", language=language),
        REQUEST_STATUS_CLARIFICATION: get_text("request_status.keyboards.status_clarification", language=language),
        REQUEST_STATUS_COMPLETED: get_text("request_status.keyboards.status_completed", language=language),
        REQUEST_STATUS_APPROVED: get_text("request_status.keyboards.status_approved", language=language)
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
            text=get_text("request_status.keyboards.cancel", language=language),
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
                text=get_text("request_status.keyboards.confirm", language=language),
                callback_data="confirm_status_change"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.cancel", language=language),
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
                    text=get_text("request_status.keyboards.purchase_materials", language=language),
                    callback_data=RequestCallbackHelper.create_callback_data_with_request_number("purchase_materials_", request_number)
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_text("request_status.keyboards.request_clarification", language=language),
                    callback_data=RequestCallbackHelper.create_callback_data_with_request_number("request_clarification_", request_number)
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_text("request_status.keyboards.complete_work", language=language),
                    callback_data=RequestCallbackHelper.create_callback_data_with_request_number("complete_work_", request_number)
                )
            ]
        ])
    elif current_status == REQUEST_STATUS_PURCHASE:
        keyboard.append([
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.return_to_work", language=language),
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("return_to_work_", request_number)
            )
        ])
    elif current_status == REQUEST_STATUS_COMPLETED:
        keyboard.append([
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.view_report", language=language),
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("view_report_", request_number)
            )
        ])

    # Общие действия
    keyboard.extend([
        [
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.add_comment", language=language),
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("add_comment_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.view_comments", language=language),
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("view_comments_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.back_to_requests", language=language),
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
                    text=get_text("request_status.keyboards.assign_request", language=language),
                    callback_data=RequestCallbackHelper.create_callback_data_with_request_number("assign_request_", request_number)
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_text("request_status.keyboards.take_to_work", language=language),
                    callback_data=f"status_{REQUEST_STATUS_IN_PROGRESS}"
                )
            ]
        ])
    elif current_status == REQUEST_STATUS_IN_PROGRESS:
        keyboard.extend([
            [
                InlineKeyboardButton(
                    text=get_text("request_status.keyboards.request_clarification", language=language),
                    callback_data=f"status_{REQUEST_STATUS_CLARIFICATION}"
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_text("request_status.keyboards.complete_work", language=language),
                    callback_data=f"status_{REQUEST_STATUS_COMPLETED}"
                )
            ]
        ])
    elif current_status == REQUEST_STATUS_PURCHASE:
        keyboard.append([
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.return_to_work", language=language),
                callback_data=f"status_{REQUEST_STATUS_IN_PROGRESS}"
            )
        ])
    elif current_status == REQUEST_STATUS_CLARIFICATION:
        keyboard.append([
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.return_to_work", language=language),
                callback_data=f"status_{REQUEST_STATUS_IN_PROGRESS}"
            )
        ])
    elif current_status == REQUEST_STATUS_COMPLETED:
        keyboard.append([
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.accept_work", language=language),
                callback_data=f"status_{REQUEST_STATUS_APPROVED}"
            )
        ])

    # Общие действия
    keyboard.extend([
        [
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.add_comment", language=language),
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("add_comment_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.view_comments", language=language),
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("view_comments_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.view_assignments", language=language),
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("view_assignments_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.back_to_requests", language=language),
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
                text=get_text("request_status.keyboards.accept_work", language=language),
                callback_data=f"status_{REQUEST_STATUS_APPROVED}"
            )
        ])

    # Общие действия
    keyboard.extend([
        [
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.view_comments", language=language),
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("view_comments_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.view_report_stats", language=language),
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("view_report_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.back_to_requests", language=language),
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
                text=get_text("request_status.keyboards.quick_in_progress", language=language),
                callback_data=f"quick_status_{REQUEST_STATUS_IN_PROGRESS}_{request_number}"
            ),
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.quick_clarification", language=language),
                callback_data=f"quick_status_{REQUEST_STATUS_CLARIFICATION}_{request_number}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.quick_completed", language=language),
                callback_data=f"quick_status_{REQUEST_STATUS_COMPLETED}_{request_number}"
            ),
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.quick_approved", language=language),
                callback_data=f"quick_status_{REQUEST_STATUS_APPROVED}_{request_number}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.comment", language=language),
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("add_comment_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_status.keyboards.cancel", language=language),
                callback_data="cancel_status_change"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
