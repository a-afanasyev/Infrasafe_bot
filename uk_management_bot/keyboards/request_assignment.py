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

def get_request_actions_keyboard(request_number: str, language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура действий с заявкой (для менеджеров)

    Args:
        request_number: Номер заявки
        language: Язык интерфейса

    Returns:
        InlineKeyboardMarkup: Клавиатура с действиями
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text=get_text("request_assignment.keyboards.assign_request", language=language),
                callback_data=f"assign_request_{request_number}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_assignment.keyboards.view_assignments", language=language),
                callback_data=f"view_assignments_{request_number}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_assignment.keyboards.add_comment", language=language),
                callback_data=f"add_comment_{request_number}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_assignment.keyboards.change_status", language=language),
                callback_data=f"change_status_{request_number}"
            )
        ]
    ]

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_executor_requests_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура "Мои заявки" для исполнителей
    
    Args:
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с действиями исполнителя
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text=get_text("request_assignment.keyboards.my_requests", language=language),
                callback_data="my_requests"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_assignment.keyboards.statistics", language=language),
                callback_data="executor_stats"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_assignment.keyboards.back", language=language),
                callback_data="back_to_main"
            )
        ]
    ]

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_request_executor_actions_keyboard(request_number: int, status: str, language: str = "ru") -> InlineKeyboardMarkup:
    """
    Клавиатура действий исполнителя с заявкой
    
    Args:
        request_number: ID заявки
        status: Текущий статус заявки
        language: Язык интерфейса
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с действиями исполнителя
    """
    keyboard = []
    
    # Действия в зависимости от статуса
    if status == "В работе":
        keyboard.extend([
            [
                InlineKeyboardButton(
                    text=get_text("request_assignment.keyboards.purchase_materials", language=language),
                    callback_data=f"purchase_materials_{request_number}"
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_text("request_assignment.keyboards.request_clarification", language=language),
                    callback_data=f"request_clarification_{request_number}"
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_text("request_assignment.keyboards.complete_work", language=language),
                    callback_data=f"complete_work_{request_number}"
                )
            ]
        ])
    elif status == "Закуп":
        keyboard.append([
            InlineKeyboardButton(
                text=get_text("request_assignment.keyboards.return_to_work", language=language),
                callback_data=f"return_to_work_{request_number}"
            )
        ])

    # Общие действия
    keyboard.extend([
        [
            InlineKeyboardButton(
                text=get_text("request_assignment.keyboards.add_comment", language=language),
                callback_data=f"add_comment_{request_number}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_assignment.keyboards.view_comments", language=language),
                callback_data=f"view_comments_{request_number}"
            )
        ],
        [
            InlineKeyboardButton(
                text=get_text("request_assignment.keyboards.back_to_requests", language=language),
                callback_data="back_to_requests"
            )
        ]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
