from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any, Optional
from datetime import datetime, date
import calendar

from uk_management_bot.services.specialization_planning_service import SPECIALIZATION_CONFIGS


def get_quarterly_planning_menu() -> InlineKeyboardMarkup:
    """Главное меню квартального планирования."""
    keyboard = [
        [InlineKeyboardButton(text="📅 Создать план на квартал", callback_data="qp_create_plan")],
        [InlineKeyboardButton(text="📊 Текущие планы", callback_data="qp_current_plans")],
        [InlineKeyboardButton(text="🔄 Управление передачами", callback_data="qp_manage_transfers")],
        [InlineKeyboardButton(text="📈 Статистика планирования", callback_data="qp_statistics")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_quarter_selection_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора квартала для планирования."""
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    current_quarter = (current_month - 1) // 3 + 1
    
    keyboard = []
    
    # Текущий год
    quarters = [
        ("I квартал", f"qp_quarter_{current_year}_1", 1, 3),
        ("II квартал", f"qp_quarter_{current_year}_2", 4, 6),
        ("III квартал", f"qp_quarter_{current_year}_3", 7, 9),
        ("IV квартал", f"qp_quarter_{current_year}_4", 10, 12),
    ]
    
    for i, (text, callback_data, start_month, end_month) in enumerate(quarters, 1):
        # Добавляем индикатор для текущего квартала
        if i == current_quarter:
            text = f"🔹 {text} (текущий)"
        # Отмечаем прошедшие кварталы
        elif i < current_quarter:
            text = f"⏸️ {text}"
            
        keyboard.append([InlineKeyboardButton(text=text, callback_data=callback_data)])
    
    # Следующий год
    next_year = current_year + 1
    keyboard.append([InlineKeyboardButton(text=f"📅 {next_year} год", callback_data=f"qp_year_{next_year}")])
    
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="qp_main_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_year_quarters_keyboard(year: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора квартала для конкретного года."""
    keyboard = []
    
    quarters = [
        (f"I квартал {year}", f"qp_quarter_{year}_1"),
        (f"II квартал {year}", f"qp_quarter_{year}_2"),
        (f"III квартал {year}", f"qp_quarter_{year}_3"),
        (f"IV квартал {year}", f"qp_quarter_{year}_4"),
    ]
    
    for text, callback_data in quarters:
        keyboard.append([InlineKeyboardButton(text=text, callback_data=callback_data)])
    
    keyboard.append([InlineKeyboardButton(text="◀️ Назад к выбору", callback_data="qp_select_quarter")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_specialization_selection_keyboard(selected: Optional[List[str]] = None) -> InlineKeyboardMarkup:
    """Клавиатура выбора специализаций для планирования."""
    if selected is None:
        selected = []
    
    keyboard = []
    
    # Группируем специализации по категориям
    categories = {
        "🔧 Технические": ["сантехника", "электрика", "слесарные_работы", "мелкий_ремонт"],
        "🏠 Обслуживание": ["уборка", "вывоз_мусора", "дезинфекция", "озеленение"],
        "🔒 Безопасность": ["охрана", "видеонаблюдение", "контроль_доступа"],
        "📋 Управление": ["управляющий"]
    }
    
    for category, specs in categories.items():
        keyboard.append([InlineKeyboardButton(text=category, callback_data="qp_category_header")])
        
        for spec in specs:
            if spec in SPECIALIZATION_CONFIGS:
                config = SPECIALIZATION_CONFIGS[spec]
                # Показываем тип графика для каждой специализации
                schedule_emoji = {
                    "duty_24_3": "🌙",  # Сутки через трое
                    "workday_5_2": "📅",  # 5/2
                    "shift_2_2": "⚡",    # 2/2
                    "flexible": "🔄"       # Гибкий
                }.get(config.schedule_type.value, "⚪")
                
                selected_emoji = "✅" if spec in selected else "⚪"
                text = f"{selected_emoji} {schedule_emoji} {spec.replace('_', ' ').title()}"
                keyboard.append([InlineKeyboardButton(
                    text=text, 
                    callback_data=f"qp_toggle_spec_{spec}"
                )])
    
    # Кнопки управления
    management_buttons = []
    if selected:
        management_buttons.append(InlineKeyboardButton(
            text="✅ Все выбранные", 
            callback_data="qp_select_all_chosen"
        ))
        management_buttons.append(InlineKeyboardButton(
            text="❌ Очистить", 
            callback_data="qp_clear_selection"
        ))
    
    management_buttons.append(InlineKeyboardButton(
        text="🔘 Выбрать все", 
        callback_data="qp_select_all"
    ))
    
    if management_buttons:
        # Разбиваем на строки по 2 кнопки
        for i in range(0, len(management_buttons), 2):
            keyboard.append(management_buttons[i:i+2])
    
    # Кнопки навигации
    if selected:
        keyboard.append([InlineKeyboardButton(
            text=f"➡️ Продолжить ({len(selected)} выбрано)", 
            callback_data="qp_confirm_specializations"
        )])
    
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="qp_select_quarter")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_planning_confirmation_keyboard(year: int, quarter: int, specializations: List[str]) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения создания плана."""
    keyboard = []
    
    # Информационная строка
    quarter_months = {
        1: "Янв-Мар",
        2: "Апр-Июн", 
        3: "Июл-Сен",
        4: "Окт-Дек"
    }
    
    period_text = f"{quarter_months[quarter]} {year}"
    
    # Основные действия
    keyboard.extend([
        [InlineKeyboardButton(text="✅ Создать план", callback_data="qp_execute_planning")],
        [InlineKeyboardButton(text="⚙️ Дополнительные настройки", callback_data="qp_advanced_settings")],
        [InlineKeyboardButton(text="📋 Предпросмотр", callback_data="qp_preview_plan")],
    ])
    
    # Настройки покрытия
    keyboard.append([
        InlineKeyboardButton(text="🌙 24/7 покрытие", callback_data="qp_toggle_247"),
        InlineKeyboardButton(text="⚖️ Балансировка нагрузки", callback_data="qp_toggle_balance")
    ])
    
    # Навигация
    keyboard.extend([
        [InlineKeyboardButton(text="✏️ Изменить специализации", callback_data="qp_edit_specializations")],
        [InlineKeyboardButton(text="📅 Изменить период", callback_data="qp_select_quarter")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="qp_back_to_specs")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_planning_results_keyboard(plan_id: Optional[int] = None, has_conflicts: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для работы с результатами планирования."""
    keyboard = []
    
    if plan_id:
        # Действия с созданным планом
        keyboard.extend([
            [InlineKeyboardButton(text="📊 Подробная статистика", callback_data=f"qp_plan_stats_{plan_id}")],
            [InlineKeyboardButton(text="📋 Экспорт расписания", callback_data=f"qp_export_plan_{plan_id}")],
            [InlineKeyboardButton(text="👥 Уведомить сотрудников", callback_data=f"qp_notify_employees_{plan_id}")],
        ])
        
        if has_conflicts:
            keyboard.append([InlineKeyboardButton(
                text="⚠️ Разрешить конфликты", 
                callback_data=f"qp_resolve_conflicts_{plan_id}"
            )])
        
        # Действия изменения
        keyboard.extend([
            [InlineKeyboardButton(text="✏️ Корректировать план", callback_data=f"qp_adjust_plan_{plan_id}")],
            [InlineKeyboardButton(text="🔄 Пересчитать", callback_data=f"qp_recalculate_{plan_id}")],
        ])
    
    # Общие действия
    keyboard.extend([
        [InlineKeyboardButton(text="📅 Создать новый план", callback_data="qp_create_plan")],
        [InlineKeyboardButton(text="📈 Аналитика", callback_data="qp_analytics")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="qp_main_menu")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_transfer_management_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления передачами смен."""
    keyboard = [
        [InlineKeyboardButton(text="🔄 Активные передачи", callback_data="qp_active_transfers")],
        [InlineKeyboardButton(text="⏳ Ожидающие передачи", callback_data="qp_pending_transfers")],
        [InlineKeyboardButton(text="✅ История передач", callback_data="qp_transfer_history")],
        [InlineKeyboardButton(text="➕ Инициировать передачу", callback_data="qp_initiate_transfer")],
        [InlineKeyboardButton(text="🔍 Поиск передач", callback_data="qp_search_transfers")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="qp_main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_statistics_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура статистики планирования."""
    keyboard = [
        [InlineKeyboardButton(text="📊 Эффективность планов", callback_data="qp_stats_efficiency")],
        [InlineKeyboardButton(text="👥 Загруженность сотрудников", callback_data="qp_stats_workload")],
        [InlineKeyboardButton(text="🎯 Покрытие специализаций", callback_data="qp_stats_coverage")],
        [InlineKeyboardButton(text="⏱️ Временные метрики", callback_data="qp_stats_timing")],
        [InlineKeyboardButton(text="💡 Рекомендации", callback_data="qp_stats_recommendations")],
        [InlineKeyboardButton(text="📈 Экспорт отчета", callback_data="qp_export_stats")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="qp_main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_advanced_settings_keyboard(settings: Dict[str, Any] = None) -> InlineKeyboardMarkup:
    """Клавиатура дополнительных настроек планирования."""
    if settings is None:
        settings = {}
    
    keyboard = []
    
    # Настройки покрытия
    coverage_24_7 = settings.get("coverage_24_7", False)
    coverage_text = "✅" if coverage_24_7 else "❌"
    keyboard.append([InlineKeyboardButton(
        text=f"{coverage_text} 24/7 покрытие", 
        callback_data="qp_toggle_coverage_247"
    )])
    
    # Балансировка нагрузки
    load_balancing = settings.get("load_balancing", True)
    balance_text = "✅" if load_balancing else "❌"
    keyboard.append([InlineKeyboardButton(
        text=f"{balance_text} Балансировка нагрузки", 
        callback_data="qp_toggle_load_balancing"
    )])
    
    # Автоматические передачи
    auto_transfers = settings.get("auto_transfers", True)
    transfer_text = "✅" if auto_transfers else "❌"
    keyboard.append([InlineKeyboardButton(
        text=f"{transfer_text} Авто-передачи", 
        callback_data="qp_toggle_auto_transfers"
    )])
    
    # Уведомления
    notifications = settings.get("notifications", True)
    notify_text = "✅" if notifications else "❌"
    keyboard.append([InlineKeyboardButton(
        text=f"{notify_text} Уведомления", 
        callback_data="qp_toggle_notifications"
    )])
    
    # Настройки периодов
    keyboard.extend([
        [InlineKeyboardButton(text="⏰ Рабочие часы", callback_data="qp_set_work_hours")],
        [InlineKeyboardButton(text="📅 Исключения в календаре", callback_data="qp_calendar_exceptions")],
        [InlineKeyboardButton(text="🔄 Ротация смен", callback_data="qp_shift_rotation_settings")],
    ])
    
    # Применить и вернуться
    keyboard.extend([
        [InlineKeyboardButton(text="💾 Сохранить настройки", callback_data="qp_save_settings")],
        [InlineKeyboardButton(text="🔄 Сбросить по умолчанию", callback_data="qp_reset_settings")],
        [InlineKeyboardButton(text="◀️ Назад к плану", callback_data="qp_back_to_confirmation")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_plan_preview_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура предпросмотра плана."""
    keyboard = [
        [InlineKeyboardButton(text="📅 Календарный вид", callback_data="qp_preview_calendar")],
        [InlineKeyboardButton(text="👥 По сотрудникам", callback_data="qp_preview_employees")],
        [InlineKeyboardButton(text="🔧 По специализациям", callback_data="qp_preview_specializations")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="qp_preview_stats")],
        [InlineKeyboardButton(text="⚠️ Конфликты", callback_data="qp_preview_conflicts")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="qp_back_to_confirmation")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_conflict_resolution_keyboard(conflict_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для разрешения конфликтов в планировании."""
    keyboard = [
        [InlineKeyboardButton(text="✅ Автоматическое решение", callback_data=f"qp_auto_resolve_{conflict_id}")],
        [InlineKeyboardButton(text="👤 Выбрать исполнителя", callback_data=f"qp_choose_executor_{conflict_id}")],
        [InlineKeyboardButton(text="⏰ Изменить время", callback_data=f"qp_change_time_{conflict_id}")],
        [InlineKeyboardButton(text="❌ Пропустить конфликт", callback_data=f"qp_skip_conflict_{conflict_id}")],
        [InlineKeyboardButton(text="📋 Детали конфликта", callback_data=f"qp_conflict_details_{conflict_id}")],
        [InlineKeyboardButton(text="◀️ К списку конфликтов", callback_data="qp_conflicts_list")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)