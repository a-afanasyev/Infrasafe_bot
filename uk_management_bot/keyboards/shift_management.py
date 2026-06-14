"""
Клавиатуры для управления сменами (менеджеры)
"""

from datetime import date, timedelta
from typing import List

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from uk_management_bot.database.models.shift_template import ShiftTemplate
from uk_management_bot.utils.helpers import get_text


def get_main_shift_menu(language: str = "ru") -> InlineKeyboardMarkup:
    """Главное меню управления сменами"""
    keyboard = [
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.shift_planning", language=language), callback_data="shift_planning")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.analytics_reports", language=language), callback_data="shift_analytics")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.template_management", language=language), callback_data="template_management")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.assign_executors", language=language), callback_data="shift_executor_assignment")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_planning_menu(language: str = "ru") -> InlineKeyboardMarkup:
    """Меню планирования смен"""
    keyboard = [
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.create_from_template", language=language), callback_data="create_shift_from_template")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.plan_week", language=language), callback_data="plan_weekly_schedule")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.auto_planning", language=language), callback_data="auto_planning")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.view_schedule", language=language), callback_data="view_schedule")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.back", language=language), callback_data="back_to_shifts")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_template_selection_keyboard(templates: List[ShiftTemplate], language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора шаблона смены"""
    keyboard = []

    for template in templates:
        # Формируем описание шаблона
        time_info = f"{template.start_hour:02d}:{template.start_minute or 0:02d}"
        duration_info = get_text("shift_management.keyboards.duration_hours", language=language).format(hours=template.duration_hours)

        specialization_info = ""
        if template.required_specializations:
            if len(template.required_specializations) == 1:
                specialization_info = f" • {template.required_specializations[0]}"
            else:
                specialization_info = " • " + get_text("shift_management.keyboards.specializations_count", language=language).format(count=len(template.required_specializations))

        button_text = f"{template.name} ({time_info}, {duration_info}{specialization_info})"

        keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"select_template:{template.id}"
            )
        ])

    # Кнопка назад
    keyboard.append([InlineKeyboardButton(text=get_text("shift_management.keyboards.back", language=language), callback_data="back_to_planning")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_date_selection_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора даты"""
    keyboard = []
    today = date.today()

    # Предлагаем выбрать дату от сегодня до следующих 14 дней
    for i in range(15):
        target_date = today + timedelta(days=i)

        if i == 0:
            date_text = get_text("shift_management.keyboards.today", language=language)
        elif i == 1:
            date_text = get_text("shift_management.keyboards.tomorrow", language=language)
        else:
            date_text = target_date.strftime("%d.%m (%A)")

        full_date_text = get_text("shift_management.keyboards.date_entry", language=language).format(date_text=date_text, date_formatted=target_date.strftime("%d.%m.%Y"))

        keyboard.append([
            InlineKeyboardButton(
                text=full_date_text,
                callback_data=f"select_date:{i}"
            )
        ])

    # Кнопка назад
    keyboard.append([InlineKeyboardButton(text=get_text("shift_management.keyboards.back", language=language), callback_data="back_to_planning")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_analytics_menu(language: str = "ru") -> InlineKeyboardMarkup:
    """Меню аналитики смен"""
    keyboard = [
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.weekly_analytics", language=language), callback_data="weekly_analytics")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.monthly_report", language=language), callback_data="monthly_analytics")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.workload_forecast", language=language), callback_data="workload_forecast")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.optimization_recommendations", language=language), callback_data="optimization_recommendations")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.efficiency_analysis", language=language), callback_data="efficiency_analysis")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.back", language=language), callback_data="back_to_shifts")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_shift_details_keyboard(shift, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для просмотра деталей смены"""
    keyboard = []

    # Действия в зависимости от статуса смены
    if shift.status == 'planned':
        keyboard.extend([
            [InlineKeyboardButton(text=get_text("shift_management.keyboards.edit", language=language), callback_data=f"edit_shift:{shift.id}")],
            [InlineKeyboardButton(text=get_text("shift_management.keyboards.assign_executor", language=language), callback_data=f"assign_executor:{shift.id}")],
            [InlineKeyboardButton(text=get_text("shift_management.keyboards.cancel", language=language), callback_data=f"cancel_shift:{shift.id}")]
        ])
    elif shift.status == 'active':
        keyboard.extend([
            [InlineKeyboardButton(text=get_text("shift_management.keyboards.view_requests", language=language), callback_data=f"view_shift_requests:{shift.id}")],
            [InlineKeyboardButton(text=get_text("shift_management.keyboards.contact_executor", language=language), callback_data=f"contact_executor:{shift.id}")],
            [InlineKeyboardButton(text=get_text("shift_management.keyboards.end_early", language=language), callback_data=f"end_shift_early:{shift.id}")]
        ])
    elif shift.status == 'completed':
        keyboard.extend([
            [InlineKeyboardButton(text=get_text("shift_management.keyboards.shift_report", language=language), callback_data=f"shift_report:{shift.id}")],
            [InlineKeyboardButton(text=get_text("shift_management.keyboards.completed_requests", language=language), callback_data=f"completed_requests:{shift.id}")],
            [InlineKeyboardButton(text=get_text("shift_management.keyboards.rate_executor", language=language), callback_data=f"rate_executor:{shift.id}")]
        ])

    # Общие действия
    keyboard.extend([
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.export_data", language=language), callback_data=f"export_shift:{shift.id}")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.back", language=language), callback_data="back_to_shifts")]
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_executor_selection_keyboard(available_executors: List, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора исполнителя для смены"""
    keyboard = []

    for executor in available_executors:
        # Формируем информацию об исполнителе
        executor_name = f"{executor.first_name} {executor.last_name or ''}".strip()

        # Добавляем специализации (если есть)
        specialization_info = ""
        if hasattr(executor, 'specializations') and executor.specializations:
            if isinstance(executor.specializations, list) and executor.specializations:
                specialization_info = f" • {executor.specializations[0]}"
                if len(executor.specializations) > 1:
                    specialization_info += f" (+{len(executor.specializations)-1})"

        # Статус доступности
        availability_emoji = "🟢"  # По умолчанию доступен

        button_text = f"{availability_emoji} {executor_name}{specialization_info}"

        keyboard.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"assign_to_executor:{executor.telegram_id}"
            )
        ])

    # Кнопки управления
    keyboard.extend([
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.auto_assign", language=language), callback_data="auto_assign_executor")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.back", language=language), callback_data="back_to_planning")]
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_schedule_view_keyboard(current_date: date, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура навигации по расписанию"""
    keyboard = []

    # Навигация по датам
    prev_date = current_date - timedelta(days=1)
    next_date = current_date + timedelta(days=1)

    keyboard.append([
        InlineKeyboardButton(text=get_text("shift_management.keyboards.previous_day", language=language), callback_data=f"schedule_date:{prev_date.isoformat()}"),
        InlineKeyboardButton(text=get_text("shift_management.keyboards.next_day", language=language), callback_data=f"schedule_date:{next_date.isoformat()}")
    ])

    # Быстрые переходы
    today = date.today()
    tomorrow = today + timedelta(days=1)

    keyboard.append([
        InlineKeyboardButton(text=get_text("shift_management.keyboards.today", language=language), callback_data=f"schedule_date:{today.isoformat()}"),
        InlineKeyboardButton(text=get_text("shift_management.keyboards.tomorrow_short", language=language), callback_data=f"schedule_date:{tomorrow.isoformat()}")
    ])

    # Переключение режимов просмотра
    keyboard.extend([
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.weekly_schedule", language=language), callback_data="schedule_week_view")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.monthly_overview", language=language), callback_data="schedule_month_view")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.back", language=language), callback_data="back_to_planning")]
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_auto_planning_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура автоматического планирования"""
    keyboard = [
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.auto_plan_week", language=language), callback_data="auto_plan_week")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.auto_plan_month", language=language), callback_data="auto_plan_month")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.create_shifts_tomorrow", language=language), callback_data="auto_plan_tomorrow")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.back", language=language), callback_data="back_to_planning")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_template_management_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура управления шаблонами смен"""
    keyboard = [
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.view_all_templates", language=language), callback_data="templates_view_all")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.create_new_template", language=language), callback_data="create_new_template")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.edit_templates", language=language), callback_data="templates_edit")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.usage_statistics", language=language), callback_data="template_usage_stats")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.import_templates", language=language), callback_data="import_templates")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.export_templates", language=language), callback_data="export_templates")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.back", language=language), callback_data="back_to_shifts")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_executor_assignment_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура назначения исполнителей"""
    keyboard = [
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.assign_to_specific_shift", language=language), callback_data="assign_to_shift")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.bulk_assignment", language=language), callback_data="bulk_assignment")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.ai_assignment", language=language), callback_data="ai_assignment")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.redistribute_load", language=language), callback_data="redistribute_load")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.workload_analysis", language=language), callback_data="workload_analysis")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.schedule_conflicts", language=language), callback_data="schedule_conflicts")],
        [InlineKeyboardButton(text=get_text("shift_management.keyboards.back", language=language), callback_data="back_to_shifts")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_confirmation_keyboard(action: str, item_id: str, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    keyboard = [
        [
            InlineKeyboardButton(text=get_text("shift_management.keyboards.confirm", language=language), callback_data=f"confirm_{action}:{item_id}"),
            InlineKeyboardButton(text=get_text("shift_management.keyboards.cancel_action", language=language), callback_data=f"cancel_{action}:{item_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
