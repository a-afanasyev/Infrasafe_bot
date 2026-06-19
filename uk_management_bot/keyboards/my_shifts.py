"""
Клавиатуры для исполнителей - интерфейс "Мои смены"
"""

from datetime import date, timedelta
from typing import List

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.utils.helpers import get_text


def get_my_shifts_menu(language: str = "ru") -> InlineKeyboardMarkup:
    """Главное меню моих смен"""

    # QA-01: "time_tracking" и "my_statistics" удалены — на эти callback'и не было
    # ни одного зарегистрированного хендлера (клик молча игнорировался). Клавиатуры
    # get_time_tracking_keyboard/get_statistics_keyboard остаются как заготовки до
    # реализации соответствующих фич (отдельная задача).
    keyboard = [
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.current_shifts", language=language), callback_data="view_current_shifts")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.week_schedule", language=language), callback_data="view_week_schedule")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.shift_history", language=language), callback_data="shift_history")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.shift_transfer", language=language), callback_data="shift_transfer_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_shift_list_keyboard(shifts: List[Shift], language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура со списком смен"""
    keyboard = []

    for shift in shifts:
        # Формируем описание смены
        shift_date = shift.planned_start_time.date()
        today = date.today()
        tomorrow = today + timedelta(days=1)

        if shift_date == today:
            date_prefix = "🔥"
        elif shift_date == tomorrow:
            date_prefix = "📅"
        else:
            date_prefix = "📆"

        start_time = shift.planned_start_time.strftime("%H:%M")
        end_time = shift.planned_end_time.strftime("%H:%M") if shift.planned_end_time else "?"

        status_emoji = {
            'planned': '⏱️',
            'active': '🔴',
            'completed': '✅',
            'cancelled': '❌'
        }.get(shift.status, '⚪')

        # Краткое описание специализации
        spec_info = ""
        if shift.specialization_focus and len(shift.specialization_focus) > 0:
            spec_info = f" • {shift.specialization_focus[0]}"
            if len(shift.specialization_focus) > 1:
                spec_info += f" (+{len(shift.specialization_focus)-1})"

        button_text = f"{date_prefix} {start_time}-{end_time} {status_emoji}{spec_info}"

        keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"shift_details:{shift.id}"
            )
        ])

    # Кнопки навигации
    keyboard.extend([
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.refresh", language=language), callback_data="view_current_shifts")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.back", language=language), callback_data="back_to_my_shifts")]
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_shift_actions_keyboard(shift: Shift, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура действий со сменой"""
    keyboard = []

    # Действия в зависимости от статуса смены
    if shift.status == 'planned':
        # Смена запланирована - можно начать или передать
        keyboard.extend([
            [InlineKeyboardButton(text=get_text("my_shifts.keyboards.start_shift", language=language), callback_data="start_shift")],
            [InlineKeyboardButton(text=get_text("my_shifts.keyboards.transfer_shift", language=language), callback_data=f"transfer_shift:{shift.id}")],
            [InlineKeyboardButton(text=get_text("my_shifts.keyboards.contact_manager", language=language), callback_data=f"contact_manager:{shift.id}")],
            [InlineKeyboardButton(text=get_text("my_shifts.keyboards.decline_shift", language=language), callback_data=f"decline_shift:{shift.id}")]
        ])

    elif shift.status == 'active':
        # Смена активна - можно завершить и работать с заявками
        keyboard.extend([
            [InlineKeyboardButton(text=get_text("my_shifts.keyboards.end_shift", language=language), callback_data="end_shift")],
            [InlineKeyboardButton(text=get_text("my_shifts.keyboards.my_requests", language=language), callback_data=f"shift_requests:{shift.id}")],
            [InlineKeyboardButton(text=get_text("my_shifts.keyboards.take_break", language=language), callback_data="take_break")],
            [InlineKeyboardButton(text=get_text("my_shifts.keyboards.transfer_shift", language=language), callback_data=f"transfer_shift:{shift.id}")]
        ])

        # Дополнительные действия
        keyboard.extend([
            [
                InlineKeyboardButton(text=get_text("my_shifts.keyboards.mark_location", language=language), callback_data="mark_location"),
                InlineKeyboardButton(text=get_text("my_shifts.keyboards.add_note", language=language), callback_data="add_note")
            ],
            [InlineKeyboardButton(text=get_text("my_shifts.keyboards.emergency_help", language=language), callback_data="emergency_help")]
        ])

    elif shift.status == 'completed':
        # Смена завершена - просмотр результатов
        keyboard.extend([
            [InlineKeyboardButton(text=get_text("my_shifts.keyboards.shift_report", language=language), callback_data=f"view_shift_report:{shift.id}")],
            [InlineKeyboardButton(text=get_text("my_shifts.keyboards.processed_requests", language=language), callback_data=f"completed_requests:{shift.id}")],
            [InlineKeyboardButton(text=get_text("my_shifts.keyboards.payment_calculation", language=language), callback_data=f"payment_calculation:{shift.id}")]
        ])

    # Общие действия (доступны всегда)
    keyboard.extend([
        [
            InlineKeyboardButton(text=get_text("my_shifts.keyboards.details", language=language), callback_data=f"shift_info:{shift.id}"),
            InlineKeyboardButton(text=get_text("my_shifts.keyboards.share", language=language), callback_data=f"share_shift:{shift.id}")
        ],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.back_to_list", language=language), callback_data="view_current_shifts")]
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_shift_filter_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура фильтров смен"""
    keyboard = [
        [
            InlineKeyboardButton(text=get_text("my_shifts.keyboards.filter_today", language=language), callback_data="filter_today"),
            InlineKeyboardButton(text=get_text("my_shifts.keyboards.filter_tomorrow", language=language), callback_data="filter_tomorrow")
        ],
        [
            InlineKeyboardButton(text=get_text("my_shifts.keyboards.filter_this_week", language=language), callback_data="filter_this_week"),
            InlineKeyboardButton(text=get_text("my_shifts.keyboards.filter_next_week", language=language), callback_data="filter_next_week")
        ],
        [
            InlineKeyboardButton(text=get_text("my_shifts.keyboards.filter_planned", language=language), callback_data="filter_planned"),
            InlineKeyboardButton(text=get_text("my_shifts.keyboards.filter_active", language=language), callback_data="filter_active")
        ],
        [
            InlineKeyboardButton(text=get_text("my_shifts.keyboards.filter_completed", language=language), callback_data="filter_completed"),
            InlineKeyboardButton(text=get_text("my_shifts.keyboards.filter_all", language=language), callback_data="filter_all")
        ],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.back", language=language), callback_data="back_to_my_shifts")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_time_tracking_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура учета времени"""
    keyboard = [
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.start_time_tracking", language=language), callback_data="start_time_tracking")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.pause_time_tracking", language=language), callback_data="pause_time_tracking")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.stop_time_tracking", language=language), callback_data="stop_time_tracking")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.time_summary", language=language), callback_data="time_summary")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.time_history", language=language), callback_data="time_history")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.back", language=language), callback_data="back_to_my_shifts")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_statistics_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура статистики исполнителя"""
    keyboard = [
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.stats_week", language=language), callback_data="stats_week")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.stats_month", language=language), callback_data="stats_month")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.stats_requests", language=language), callback_data="stats_requests")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.stats_time", language=language), callback_data="stats_time")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.stats_efficiency", language=language), callback_data="stats_efficiency")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.stats_achievements", language=language), callback_data="stats_achievements")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.back", language=language), callback_data="back_to_my_shifts")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_break_options_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура опций перерыва"""
    keyboard = [
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.break_lunch", language=language), callback_data="break_lunch")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.break_short", language=language), callback_data="break_short")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.break_medical", language=language), callback_data="break_medical")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.break_custom", language=language), callback_data="break_custom")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.cancel_break", language=language), callback_data="cancel_break")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_emergency_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура экстренных ситуаций"""
    keyboard = [
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.call_emergency_services", language=language), callback_data="call_emergency_services")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.call_security", language=language), callback_data="call_security")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.technical_issue", language=language), callback_data="technical_issue")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.medical_help", language=language), callback_data="medical_help")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.contact_dispatcher", language=language), callback_data="contact_dispatcher")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.back_cancel_emergency", language=language), callback_data="cancel_emergency")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_shift_requests_keyboard(shift_id: int, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для работы с заявками смены"""
    keyboard = [
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.all_requests", language=language), callback_data=f"all_requests:{shift_id}")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.new_requests", language=language), callback_data=f"new_requests:{shift_id}")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.active_requests", language=language), callback_data=f"active_requests:{shift_id}")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.completed_requests", language=language), callback_data=f"completed_requests:{shift_id}")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.requests_by_location", language=language), callback_data=f"requests_by_location:{shift_id}")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.back_to_shift", language=language), callback_data=f"shift_details:{shift_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_location_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для отметки местоположения"""
    keyboard = [
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.send_current_location", language=language), callback_data="send_current_location")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.mark_address", language=language), callback_data="mark_address")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.location_history", language=language), callback_data="location_history")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.back_to_shift_actions", language=language), callback_data="back_to_shift_actions")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_shift_completion_keyboard(shift_id: int, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура завершения смены"""
    keyboard = [
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.confirm_end_shift", language=language), callback_data=f"confirm_end_shift:{shift_id}")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.add_shift_report", language=language), callback_data=f"add_shift_report:{shift_id}")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.shift_summary", language=language), callback_data=f"shift_summary:{shift_id}")],
        [InlineKeyboardButton(text=get_text("my_shifts.keyboards.cancel_end_shift", language=language), callback_data=f"cancel_end_shift:{shift_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_navigation_keyboard(current_page: int, total_pages: int, callback_prefix: str, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура навигации по страницам"""
    keyboard = []

    navigation_row = []

    # Кнопка "Предыдущая"
    if current_page > 1:
        navigation_row.append(
            InlineKeyboardButton(text=get_text("my_shifts.keyboards.prev_page", language=language), callback_data=f"{callback_prefix}:{current_page - 1}")
        )

    # Показатель страницы
    navigation_row.append(
        InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="page_info")
    )

    # Кнопка "Следующая"
    if current_page < total_pages:
        navigation_row.append(
            InlineKeyboardButton(text=get_text("my_shifts.keyboards.next_page", language=language), callback_data=f"{callback_prefix}:{current_page + 1}")
        )

    if navigation_row:
        keyboard.append(navigation_row)

    return InlineKeyboardMarkup(inline_keyboard=keyboard)
