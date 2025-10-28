"""
Клавиатуры для управления сменами (менеджеры)
"""

from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from uk_management_bot.database.models.shift_template import ShiftTemplate


def get_main_shift_menu(lang: str = "ru") -> InlineKeyboardMarkup:
    """Главное меню управления сменами"""
    keyboard = [
        [InlineKeyboardButton(text="📅 Планирование смен", callback_data="shift_planning")],
        [InlineKeyboardButton(text="📊 Аналитика и отчеты", callback_data="shift_analytics")],
        [InlineKeyboardButton(text="🗂️ Управление шаблонами", callback_data="template_management")],
        [InlineKeyboardButton(text="👥 Назначение исполнителей", callback_data="shift_executor_assignment")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_planning_menu(lang: str = "ru") -> InlineKeyboardMarkup:
    """Меню планирования смен"""
    keyboard = [
        [InlineKeyboardButton(text="🗂️ Создать смену из шаблона", callback_data="create_shift_from_template")],
        [InlineKeyboardButton(text="📅 Планировать неделю", callback_data="plan_weekly_schedule")],
        [InlineKeyboardButton(text="🤖 Автоматическое планирование", callback_data="auto_planning")],
        [InlineKeyboardButton(text="📋 Просмотр расписания", callback_data="view_schedule")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_shifts")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_template_selection_keyboard(templates: List[ShiftTemplate], lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора шаблона смены"""
    keyboard = []
    
    for template in templates:
        # Формируем описание шаблона
        time_info = f"{template.start_hour:02d}:{template.start_minute or 0:02d}"
        duration_info = f"{template.duration_hours}ч"
        
        specialization_info = ""
        if template.required_specializations:
            if len(template.required_specializations) == 1:
                specialization_info = f" • {template.required_specializations[0]}"
            else:
                specialization_info = f" • {len(template.required_specializations)} спец."
        
        button_text = f"{template.name} ({time_info}, {duration_info}{specialization_info})"
        
        keyboard.append([
            InlineKeyboardButton(
                text=button_text, 
                callback_data=f"select_template:{template.id}"
            )
        ])
    
    # Кнопка назад
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_planning")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_date_selection_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора даты"""
    keyboard = []
    today = date.today()
    
    # Предлагаем выбрать дату от сегодня до следующих 14 дней
    for i in range(15):
        target_date = today + timedelta(days=i)
        
        if i == 0:
            date_text = "🔥 Сегодня"
        elif i == 1:
            date_text = "📅 Завтра"
        else:
            date_text = target_date.strftime("%d.%m (%A)")
        
        full_date_text = f"{date_text} - {target_date.strftime('%d.%m.%Y')}"
        
        keyboard.append([
            InlineKeyboardButton(
                text=full_date_text, 
                callback_data=f"select_date:{i}"
            )
        ])
    
    # Кнопка назад
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_planning")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_analytics_menu(lang: str = "ru") -> InlineKeyboardMarkup:
    """Меню аналитики смен"""
    keyboard = [
        [InlineKeyboardButton(text="📊 Недельная аналитика", callback_data="weekly_analytics")],
        [InlineKeyboardButton(text="📈 Месячный отчет", callback_data="monthly_analytics")],
        [InlineKeyboardButton(text="🔮 Прогноз нагрузки", callback_data="workload_forecast")],
        [InlineKeyboardButton(text="💡 Рекомендации по оптимизации", callback_data="optimization_recommendations")],
        [InlineKeyboardButton(text="📋 Анализ эффективности", callback_data="efficiency_analysis")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_shifts")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_shift_details_keyboard(shift, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для просмотра деталей смены"""
    keyboard = []
    
    # Действия в зависимости от статуса смены
    if shift.status == 'planned':
        keyboard.extend([
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_shift:{shift.id}")],
            [InlineKeyboardButton(text="👤 Назначить исполнителя", callback_data=f"assign_executor:{shift.id}")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_shift:{shift.id}")]
        ])
    elif shift.status == 'active':
        keyboard.extend([
            [InlineKeyboardButton(text="📋 Просмотр заявок", callback_data=f"view_shift_requests:{shift.id}")],
            [InlineKeyboardButton(text="📞 Связаться с исполнителем", callback_data=f"contact_executor:{shift.id}")],
            [InlineKeyboardButton(text="⏹️ Завершить досрочно", callback_data=f"end_shift_early:{shift.id}")]
        ])
    elif shift.status == 'completed':
        keyboard.extend([
            [InlineKeyboardButton(text="📊 Отчет по смене", callback_data=f"shift_report:{shift.id}")],
            [InlineKeyboardButton(text="📋 Обработанные заявки", callback_data=f"completed_requests:{shift.id}")],
            [InlineKeyboardButton(text="📝 Оценить исполнителя", callback_data=f"rate_executor:{shift.id}")]
        ])
    
    # Общие действия
    keyboard.extend([
        [InlineKeyboardButton(text="📄 Экспорт данных", callback_data=f"export_shift:{shift.id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_shifts")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_executor_selection_keyboard(available_executors: List, lang: str = "ru") -> InlineKeyboardMarkup:
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
        [InlineKeyboardButton(text="🤖 Автоназначение", callback_data="auto_assign_executor")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_planning")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_schedule_view_keyboard(current_date: date, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура навигации по расписанию"""
    keyboard = []
    
    # Навигация по датам
    prev_date = current_date - timedelta(days=1)
    next_date = current_date + timedelta(days=1)
    
    keyboard.append([
        InlineKeyboardButton(text="⬅️ Предыдущий день", callback_data=f"schedule_date:{prev_date.isoformat()}"),
        InlineKeyboardButton(text="➡️ Следующий день", callback_data=f"schedule_date:{next_date.isoformat()}")
    ])
    
    # Быстрые переходы
    today = date.today()
    tomorrow = today + timedelta(days=1)
    
    keyboard.append([
        InlineKeyboardButton(text="🔥 Сегодня", callback_data=f"schedule_date:{today.isoformat()}"),
        InlineKeyboardButton(text="📅 Завтра", callback_data=f"schedule_date:{tomorrow.isoformat()}")
    ])
    
    # Переключение режимов просмотра
    keyboard.extend([
        [InlineKeyboardButton(text="📅 Недельное расписание", callback_data="schedule_week_view")],
        [InlineKeyboardButton(text="📊 Месячный обзор", callback_data="schedule_month_view")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_planning")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_auto_planning_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура автоматического планирования"""
    keyboard = [
        [InlineKeyboardButton(text="🤖 Автопланирование на неделю", callback_data="auto_plan_week")],
        [InlineKeyboardButton(text="📅 Автопланирование на месяц", callback_data="auto_plan_month")],
        [InlineKeyboardButton(text="⚡ Создать смены на завтра", callback_data="auto_plan_tomorrow")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_planning")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_template_management_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура управления шаблонами смен"""
    keyboard = [
        [InlineKeyboardButton(text="📋 Просмотр всех шаблонов", callback_data="templates_view_all")],
        [InlineKeyboardButton(text="➕ Создать новый шаблон", callback_data="create_new_template")],
        [InlineKeyboardButton(text="✏️ Редактировать шаблоны", callback_data="templates_edit")],
        [InlineKeyboardButton(text="📊 Статистика использования", callback_data="template_usage_stats")],
        [InlineKeyboardButton(text="📥 Импорт шаблонов", callback_data="import_templates")],
        [InlineKeyboardButton(text="📤 Экспорт шаблонов", callback_data="export_templates")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_shifts")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_executor_assignment_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура назначения исполнителей"""
    keyboard = [
        [InlineKeyboardButton(text="👤 Назначить на конкретную смену", callback_data="assign_to_shift")],
        [InlineKeyboardButton(text="📅 Массовое назначение", callback_data="bulk_assignment")],
        [InlineKeyboardButton(text="🤖 ИИ-назначение", callback_data="ai_assignment")],
        [InlineKeyboardButton(text="🔄 Перераспределить нагрузку", callback_data="redistribute_load")],
        [InlineKeyboardButton(text="📊 Анализ загруженности", callback_data="workload_analysis")],
        [InlineKeyboardButton(text="⚠️ Конфликты расписания", callback_data="schedule_conflicts")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_shifts")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_confirmation_keyboard(action: str, item_id: str, lang: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    keyboard = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{action}:{item_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_{action}:{item_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)