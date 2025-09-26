"""
FSM состояния для управления сменами (менеджеры)
"""

from aiogram.fsm.state import State, StatesGroup


class ShiftManagementStates(StatesGroup):
    """Состояния для управления сменами менеджерами"""
    
    # Основные меню
    main_menu = State()
    planning_menu = State()
    analytics_menu = State()
    template_menu = State()
    assignment_menu = State()
    
    # Планирование смен
    selecting_template = State()
    selecting_date = State()
    selecting_executor = State()
    confirming_shift_creation = State()
    
    # Просмотр расписания
    viewing_schedule = State()
    viewing_schedule_day = State()
    viewing_schedule_week = State()
    viewing_schedule_month = State()
    
    # Редактирование смен
    editing_shift = State()
    editing_shift_time = State()
    editing_shift_executor = State()
    editing_shift_notes = State()
    
    # Назначение исполнителей
    selecting_shift_for_assignment = State()
    selecting_executor_for_assignment = State()
    confirming_assignment = State()
    
    # Автоматическое планирование
    auto_planning_settings = State()
    auto_planning_confirmation = State()
    auto_planning_progress = State()
    
    # Управление шаблонами
    creating_template = State()
    template_name_input = State()
    template_time_input = State()
    template_duration_input = State()
    template_specialization_selection = State()
    template_days_selection = State()
    template_confirmation = State()
    
    # Аналитика
    viewing_analytics = State()
    generating_report = State()
    exporting_data = State()
    
    # Экстренное планирование
    emergency_planning = State()
    emergency_shift_creation = State()
    emergency_executor_search = State()


class TemplateManagementStates(StatesGroup):
    """Состояния для управления шаблонами смен"""
    
    # Основное меню шаблонов
    main_menu = State()
    viewing_templates = State()
    template_details = State()
    
    # Создание нового шаблона
    creating_template = State()
    entering_name = State()
    entering_description = State()
    setting_start_time = State()
    setting_duration = State()
    selecting_specializations = State()
    selecting_work_days = State()
    setting_executor_limits = State()
    setting_geographic_zone = State()
    setting_coverage_areas = State()
    reviewing_template = State()
    confirming_creation = State()
    
    # Редактирование шаблона
    editing_template = State()
    editing_field = State()
    confirming_changes = State()
    
    # Копирование и импорт
    copying_template = State()
    importing_templates = State()
    exporting_templates = State()


class AutoPlanningStates(StatesGroup):
    """Состояния для автоматического планирования"""
    
    # Настройки автопланирования
    settings_menu = State()
    setting_auto_create = State()
    setting_advance_days = State()
    setting_min_executors = State()
    setting_max_executors = State()
    setting_priority_level = State()
    
    # Планирование периода
    selecting_period = State()
    confirming_auto_plan = State()
    monitoring_progress = State()
    reviewing_results = State()
    
    # Экстренное планирование
    emergency_assessment = State()
    emergency_solution_selection = State()
    emergency_execution = State()


class ShiftAnalyticsStates(StatesGroup):
    """Состояния для аналитики смен"""
    
    # Основное меню аналитики
    main_menu = State()
    
    # Выбор периода анализа
    selecting_period = State()
    custom_period_start = State()
    custom_period_end = State()
    
    # Типы отчетов
    generating_weekly_report = State()
    generating_monthly_report = State()
    generating_custom_report = State()
    
    # Экспорт данных
    export_format_selection = State()
    export_parameters = State()
    export_confirmation = State()
    
    # Детализация аналитики
    viewing_efficiency_details = State()
    viewing_workload_details = State()
    viewing_executor_performance = State()
    
    # Настройка дашборда
    dashboard_customization = State()
    dashboard_widget_selection = State()


class ExecutorAssignmentStates(StatesGroup):
    """Состояния для назначения исполнителей на смены"""
    
    # Основное меню назначений
    main_menu = State()
    
    # Выбор смены для назначения
    selecting_shift = State()
    viewing_shift_details = State()
    
    # Выбор исполнителя
    viewing_available_executors = State()
    executor_details = State()
    executor_schedule_check = State()
    
    # Подтверждение назначения
    assignment_confirmation = State()
    assignment_notes_input = State()
    
    # Массовое назначение
    bulk_assignment_setup = State()
    bulk_period_selection = State()
    bulk_criteria_selection = State()
    bulk_confirmation = State()
    bulk_progress = State()
    
    # ИИ-назначение
    ai_assignment_parameters = State()
    ai_assignment_preview = State()
    ai_assignment_confirmation = State()
    ai_assignment_monitoring = State()
    
    # Перераспределение
    redistribution_analysis = State()
    redistribution_options = State()
    redistribution_confirmation = State()
    
    # Управление конфликтами
    conflict_detection = State()
    conflict_resolution = State()
    conflict_confirmation = State()