from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any, Optional
from datetime import datetime, date
import calendar

from uk_management_bot.services.specialization_planning_service import SPECIALIZATION_CONFIGS
from uk_management_bot.utils.helpers import get_text


def get_quarterly_planning_menu(language: str = "ru") -> InlineKeyboardMarkup:
    """Главное меню квартального планирования."""
    keyboard = [
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.create_plan", language=language), callback_data="qp_create_plan")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.current_plans", language=language), callback_data="qp_current_plans")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.manage_transfers", language=language), callback_data="qp_manage_transfers")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.planning_statistics", language=language), callback_data="qp_statistics")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.back", language=language), callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_quarter_selection_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора квартала для планирования."""
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    current_quarter = (current_month - 1) // 3 + 1

    keyboard = []

    # Текущий год
    quarter_keys = [
        ("quarterly.keyboards.quarter_i", f"qp_quarter_{current_year}_1", 1, 3),
        ("quarterly.keyboards.quarter_ii", f"qp_quarter_{current_year}_2", 4, 6),
        ("quarterly.keyboards.quarter_iii", f"qp_quarter_{current_year}_3", 7, 9),
        ("quarterly.keyboards.quarter_iv", f"qp_quarter_{current_year}_4", 10, 12),
    ]

    for i, (text_key, callback_data, start_month, end_month) in enumerate(quarter_keys, 1):
        text = get_text(text_key, language=language)
        # Добавляем индикатор для текущего квартала
        if i == current_quarter:
            text = get_text("quarterly.keyboards.quarter_current", language=language).format(quarter=text)
        # Отмечаем прошедшие кварталы
        elif i < current_quarter:
            text = get_text("quarterly.keyboards.quarter_past", language=language).format(quarter=text)

        keyboard.append([InlineKeyboardButton(text=text, callback_data=callback_data)])

    # Следующий год
    next_year = current_year + 1
    keyboard.append([InlineKeyboardButton(text=get_text("quarterly.keyboards.year_label", language=language).format(year=next_year), callback_data=f"qp_year_{next_year}")])

    keyboard.append([InlineKeyboardButton(text=get_text("quarterly.keyboards.back", language=language), callback_data="qp_main_menu")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_year_quarters_keyboard(year: int, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора квартала для конкретного года."""
    keyboard = []

    quarters = [
        (get_text("quarterly.keyboards.quarter_i_year", language=language).format(year=year), f"qp_quarter_{year}_1"),
        (get_text("quarterly.keyboards.quarter_ii_year", language=language).format(year=year), f"qp_quarter_{year}_2"),
        (get_text("quarterly.keyboards.quarter_iii_year", language=language).format(year=year), f"qp_quarter_{year}_3"),
        (get_text("quarterly.keyboards.quarter_iv_year", language=language).format(year=year), f"qp_quarter_{year}_4"),
    ]

    for text, callback_data in quarters:
        keyboard.append([InlineKeyboardButton(text=text, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton(text=get_text("quarterly.keyboards.back_to_selection", language=language), callback_data="qp_select_quarter")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_specialization_selection_keyboard(selected: Optional[List[str]] = None, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура выбора специализаций для планирования."""
    if selected is None:
        selected = []

    keyboard = []

    # Группируем специализации по категориям
    categories = {
        "quarterly.keyboards.cat_technical": ["сантехника", "электрика", "слесарные_работы", "мелкий_ремонт"],
        "quarterly.keyboards.cat_maintenance": ["уборка", "вывоз_мусора", "дезинфекция", "озеленение"],
        "quarterly.keyboards.cat_security": ["охрана", "видеонаблюдение", "контроль_доступа"],
        "quarterly.keyboards.cat_management": ["управляющий"]
    }

    for category_key, specs in categories.items():
        keyboard.append([InlineKeyboardButton(text=get_text(category_key, language=language), callback_data="qp_category_header")])

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
            text=get_text("quarterly.keyboards.all_selected", language=language),
            callback_data="qp_select_all_chosen"
        ))
        management_buttons.append(InlineKeyboardButton(
            text=get_text("quarterly.keyboards.clear_selection", language=language),
            callback_data="qp_clear_selection"
        ))

    management_buttons.append(InlineKeyboardButton(
        text=get_text("quarterly.keyboards.select_all", language=language),
        callback_data="qp_select_all"
    ))

    if management_buttons:
        # Разбиваем на строки по 2 кнопки
        for i in range(0, len(management_buttons), 2):
            keyboard.append(management_buttons[i:i+2])

    # Кнопки навигации
    if selected:
        keyboard.append([InlineKeyboardButton(
            text=get_text("quarterly.keyboards.continue_selected", language=language).format(count=len(selected)),
            callback_data="qp_confirm_specializations"
        )])

    keyboard.append([InlineKeyboardButton(text=get_text("quarterly.keyboards.back", language=language), callback_data="qp_select_quarter")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_planning_confirmation_keyboard(year: int, quarter: int, specializations: List[str], language: str = "ru") -> InlineKeyboardMarkup:
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
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.create_plan_confirm", language=language), callback_data="qp_execute_planning")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.advanced_settings", language=language), callback_data="qp_advanced_settings")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.preview", language=language), callback_data="qp_preview_plan")],
    ])

    # Настройки покрытия
    keyboard.append([
        InlineKeyboardButton(text=get_text("quarterly.keyboards.coverage_247", language=language), callback_data="qp_toggle_247"),
        InlineKeyboardButton(text=get_text("quarterly.keyboards.load_balancing", language=language), callback_data="qp_toggle_balance")
    ])

    # Навигация
    keyboard.extend([
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.edit_specializations", language=language), callback_data="qp_edit_specializations")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.change_period", language=language), callback_data="qp_select_quarter")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.back", language=language), callback_data="qp_back_to_specs")]
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_planning_results_keyboard(plan_id: Optional[int] = None, has_conflicts: bool = False, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для работы с результатами планирования."""
    keyboard = []

    if plan_id:
        # Действия с созданным планом
        keyboard.extend([
            [InlineKeyboardButton(text=get_text("quarterly.keyboards.detailed_stats", language=language), callback_data=f"qp_plan_stats_{plan_id}")],
            [InlineKeyboardButton(text=get_text("quarterly.keyboards.export_schedule", language=language), callback_data=f"qp_export_plan_{plan_id}")],
            [InlineKeyboardButton(text=get_text("quarterly.keyboards.notify_employees", language=language), callback_data=f"qp_notify_employees_{plan_id}")],
        ])

        if has_conflicts:
            keyboard.append([InlineKeyboardButton(
                text=get_text("quarterly.keyboards.resolve_conflicts", language=language),
                callback_data=f"qp_resolve_conflicts_{plan_id}"
            )])

        # Действия изменения
        keyboard.extend([
            [InlineKeyboardButton(text=get_text("quarterly.keyboards.adjust_plan", language=language), callback_data=f"qp_adjust_plan_{plan_id}")],
            [InlineKeyboardButton(text=get_text("quarterly.keyboards.recalculate", language=language), callback_data=f"qp_recalculate_{plan_id}")],
        ])

    # Общие действия
    keyboard.extend([
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.create_new_plan", language=language), callback_data="qp_create_plan")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.analytics", language=language), callback_data="qp_analytics")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.main_menu", language=language), callback_data="qp_main_menu")]
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_transfer_management_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура управления передачами смен."""
    keyboard = [
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.active_transfers", language=language), callback_data="qp_active_transfers")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.pending_transfers", language=language), callback_data="qp_pending_transfers")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.transfer_history", language=language), callback_data="qp_transfer_history")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.initiate_transfer", language=language), callback_data="qp_initiate_transfer")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.search_transfers", language=language), callback_data="qp_search_transfers")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.back", language=language), callback_data="qp_main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_statistics_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура статистики планирования."""
    keyboard = [
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.stats_efficiency", language=language), callback_data="qp_stats_efficiency")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.stats_workload", language=language), callback_data="qp_stats_workload")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.stats_coverage", language=language), callback_data="qp_stats_coverage")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.stats_timing", language=language), callback_data="qp_stats_timing")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.stats_recommendations", language=language), callback_data="qp_stats_recommendations")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.export_report", language=language), callback_data="qp_export_stats")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.back", language=language), callback_data="qp_main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_advanced_settings_keyboard(settings: Dict[str, Any] = None, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура дополнительных настроек планирования."""
    if settings is None:
        settings = {}

    keyboard = []

    # Настройки покрытия
    coverage_24_7 = settings.get("coverage_24_7", False)
    coverage_text = "✅" if coverage_24_7 else "❌"
    keyboard.append([InlineKeyboardButton(
        text=f"{coverage_text} {get_text('quarterly.keyboards.toggle_coverage_247', language=language)}",
        callback_data="qp_toggle_coverage_247"
    )])

    # Балансировка нагрузки
    load_balancing = settings.get("load_balancing", True)
    balance_text = "✅" if load_balancing else "❌"
    keyboard.append([InlineKeyboardButton(
        text=f"{balance_text} {get_text('quarterly.keyboards.toggle_load_balancing', language=language)}",
        callback_data="qp_toggle_load_balancing"
    )])

    # Автоматические передачи
    auto_transfers = settings.get("auto_transfers", True)
    transfer_text = "✅" if auto_transfers else "❌"
    keyboard.append([InlineKeyboardButton(
        text=f"{transfer_text} {get_text('quarterly.keyboards.toggle_auto_transfers', language=language)}",
        callback_data="qp_toggle_auto_transfers"
    )])

    # Уведомления
    notifications = settings.get("notifications", True)
    notify_text = "✅" if notifications else "❌"
    keyboard.append([InlineKeyboardButton(
        text=f"{notify_text} {get_text('quarterly.keyboards.toggle_notifications', language=language)}",
        callback_data="qp_toggle_notifications"
    )])

    # Настройки периодов
    keyboard.extend([
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.work_hours", language=language), callback_data="qp_set_work_hours")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.calendar_exceptions", language=language), callback_data="qp_calendar_exceptions")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.shift_rotation", language=language), callback_data="qp_shift_rotation_settings")],
    ])

    # Применить и вернуться
    keyboard.extend([
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.save_settings", language=language), callback_data="qp_save_settings")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.reset_defaults", language=language), callback_data="qp_reset_settings")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.back_to_plan", language=language), callback_data="qp_back_to_confirmation")]
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_plan_preview_keyboard(language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура предпросмотра плана."""
    keyboard = [
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.preview_calendar", language=language), callback_data="qp_preview_calendar")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.preview_employees", language=language), callback_data="qp_preview_employees")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.preview_specializations", language=language), callback_data="qp_preview_specializations")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.preview_stats", language=language), callback_data="qp_preview_stats")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.preview_conflicts", language=language), callback_data="qp_preview_conflicts")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.back", language=language), callback_data="qp_back_to_confirmation")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_conflict_resolution_keyboard(conflict_id: int, language: str = "ru") -> InlineKeyboardMarkup:
    """Клавиатура для разрешения конфликтов в планировании."""
    keyboard = [
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.auto_resolve", language=language), callback_data=f"qp_auto_resolve_{conflict_id}")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.choose_executor", language=language), callback_data=f"qp_choose_executor_{conflict_id}")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.change_time", language=language), callback_data=f"qp_change_time_{conflict_id}")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.skip_conflict", language=language), callback_data=f"qp_skip_conflict_{conflict_id}")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.conflict_details", language=language), callback_data=f"qp_conflict_details_{conflict_id}")],
        [InlineKeyboardButton(text=get_text("quarterly.keyboards.conflicts_list", language=language), callback_data="qp_conflicts_list")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
