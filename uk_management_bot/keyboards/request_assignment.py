"""
Клавиатуры для назначения заявок на исполнение
Создает интерактивные клавиатуры для процесса назначения заявок
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List

from uk_management_bot.database.models.user import User
from uk_management_bot.utils.helpers import get_text
from uk_management_bot.utils.request_helpers import RequestCallbackHelper

def get_request_assignment_keyboard(request_number: str, language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура выбора типа назначения заявки
    
    Args:
        request_number: Номер заявки в формате YYMMDD-NNN
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопками выбора типа назначения
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text=get_text("request_assignment.group_assignment", language=language),
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("assign_group_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_assignment.individual_assignment", language=language),
                callback_data=RequestCallbackHelper.create_callback_data_with_request_number("assign_individual_", request_number)
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("buttons.cancel", language=language),
                callback_data="cancel_assignment"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_specialization_selection_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура выбора специализации для группового назначения
    
    Args:
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопками специализаций
    """
    specializations = [
        ("сантехник", "spec_plumber"),
        ("электрик", "spec_electrician"),
        ("уборщик", "spec_cleaner"),
        ("дворник", "spec_janitor"),
        ("охранник", "spec_guard"),
        ("специалист", "spec_specialist"),
    ]

    keyboard = []
    row = []

    for spec_value, spec_key in specializations:
        row.append(InlineKeyboardButton(
            text=get_text(f"request_assignment.keyboards.{spec_key}", language=language),
            callback_data=f"specialization_{spec_value}"
        ))
        
        if len(row) == 2:  # 2 кнопки в ряду
            keyboard.append(row)
            row = []
    
    # Добавляем оставшиеся кнопки
    if row:
        keyboard.append(row)
    
    # Добавляем кнопку отмены
    keyboard.append([
        InlineKeyboardButton(
            text=get_text("request_assignment.keyboards.cancel", language=language),
            callback_data="cancel_assignment"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_executor_selection_keyboard(executors: List[User], language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура выбора конкретного исполнителя
    
    Args:
        executors: Список доступных исполнителей
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопками исполнителей
    """
    keyboard = []
    
    for executor in executors:
        keyboard.append([
            InlineKeyboardButton(
                text=get_text("request_assignment.keyboards.executor_item", language=language).format(name=executor.full_name),
                callback_data=f"executor_{executor.id}"
            )
        ])

    # Добавляем кнопку отмены
    keyboard.append([
        InlineKeyboardButton(
            text=get_text("request_assignment.keyboards.cancel", language=language),
            callback_data="cancel_assignment"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_assignment_confirmation_keyboard(assignment_type: str, language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура подтверждения назначения
    
    Args:
        assignment_type: Тип назначения ('group' или 'individual')
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопками подтверждения
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text=get_text("request_assignment.keyboards.confirm", language=language),
                callback_data="confirm_assignment"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_assignment.keyboards.cancel", language=language),
                callback_data="cancel_assignment"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# BUG-137: билдеры-сироты get_request_actions_keyboard /
# get_executor_requests_keyboard / get_request_executor_actions_keyboard
# удалены — 0 колл-сайтов вне их собственных тестов, их callback'и
# (change_status_/purchase_materials_/complete_work_) вели в ретайренный
# FSM-флоу смены статусов.
