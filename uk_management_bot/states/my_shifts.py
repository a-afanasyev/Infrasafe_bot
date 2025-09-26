"""
FSM состояния для интерфейса "Мои смены" (исполнители)
"""

from aiogram.fsm.state import State, StatesGroup


class MyShiftsStates(StatesGroup):
    """Состояния для интерфейса "Мои смены" исполнителей"""
    
    # Основные меню
    main_menu = State()
    
    # Просмотр смен
    viewing_shifts = State()
    viewing_shift_details = State()
    filtering_shifts = State()
    
    # Управление сменой
    shift_actions = State()
    confirming_shift_start = State()
    confirming_shift_end = State()
    
    # Учет времени
    time_tracking_menu = State()
    time_tracking_active = State()
    time_break = State()
    time_break_selection = State()
    time_break_custom_input = State()
    
    # Работа с заявками в смене
    viewing_shift_requests = State()
    request_details = State()
    request_actions = State()
    
    # Отчеты и заметки
    adding_shift_note = State()
    note_input = State()
    creating_shift_report = State()
    report_input = State()
    
    # Местоположение
    location_menu = State()
    marking_location = State()
    address_input = State()
    
    # Экстренные ситуации
    emergency_menu = State()
    emergency_description = State()
    emergency_contact_selection = State()
    
    # Статистика и история
    viewing_statistics = State()
    viewing_history = State()
    history_details = State()
    
    # Настройки уведомлений
    notification_settings = State()
    notification_preferences = State()


class ShiftTimeTrackingStates(StatesGroup):
    """Состояния для учета рабочего времени в смене"""
    
    # Основной учет времени
    tracking_inactive = State()
    tracking_active = State()
    tracking_paused = State()
    
    # Перерывы
    break_selection = State()
    break_active = State()
    break_custom_duration = State()
    break_reason_input = State()
    
    # Завершение учета
    finalizing_time = State()
    time_corrections = State()
    time_confirmation = State()
    
    # Отчеты времени
    time_summary = State()
    time_export = State()


class ShiftRequestHandlingStates(StatesGroup):
    """Состояния для работы с заявками во время смены"""
    
    # Просмотр заявок
    viewing_requests_list = State()
    request_details = State()
    request_filtering = State()
    
    # Принятие заявки в работу
    accepting_request = State()
    acceptance_confirmation = State()
    
    # Работа с заявкой
    request_in_progress = State()
    updating_request_status = State()
    adding_request_comment = State()
    
    # Завершение заявки
    completing_request = State()
    completion_report_input = State()
    completion_confirmation = State()
    
    # Специальные статусы
    requesting_materials = State()
    materials_list_input = State()
    requesting_clarification = State()
    clarification_input = State()
    
    # Проблемы с заявкой
    reporting_issue = State()
    issue_description = State()
    escalating_request = State()


class ShiftEmergencyStates(StatesGroup):
    """Состояния для экстренных ситуаций во время смены"""
    
    # Типы экстренных ситуаций
    emergency_type_selection = State()
    
    # Экстренные службы
    calling_emergency_services = State()
    emergency_services_confirmation = State()
    
    # Техническая помощь
    technical_issue_description = State()
    technical_help_request = State()
    
    # Медицинская помощь
    medical_issue_description = State()
    medical_help_request = State()
    
    # Связь с диспетчером
    dispatcher_contact = State()
    dispatcher_message = State()
    
    # Отчет об инциденте
    incident_report = State()
    incident_details = State()
    incident_confirmation = State()
    
    # Отслеживание статуса
    emergency_status_tracking = State()
    emergency_resolution = State()


class ShiftReportingStates(StatesGroup):
    """Состояния для отчетности по сменам"""
    
    # Создание отчета о смене
    report_creation = State()
    report_summary_input = State()
    report_achievements_input = State()
    report_issues_input = State()
    report_recommendations_input = State()
    
    # Отчет о заявках
    requests_summary = State()
    requests_statistics = State()
    
    # Отчет о времени
    time_report = State()
    efficiency_report = State()
    
    # Финализация отчета
    report_review = State()
    report_submission = State()
    
    # Просмотр отчетов
    viewing_reports = State()
    report_details = State()
    report_export = State()


class ShiftStatisticsStates(StatesGroup):
    """Состояния для просмотра статистики исполнителя"""
    
    # Основные статистики
    statistics_menu = State()
    
    # Статистика времени
    time_statistics = State()
    time_period_selection = State()
    
    # Статистика заявок
    requests_statistics = State()
    requests_performance = State()
    
    # Эффективность
    efficiency_statistics = State()
    efficiency_trends = State()
    efficiency_comparison = State()
    
    # Рейтинги и достижения
    rating_statistics = State()
    achievements_view = State()
    achievements_progress = State()
    
    # Сравнения
    peer_comparison = State()
    historical_comparison = State()
    
    # Экспорт статистики
    statistics_export = State()
    export_parameters = State()


class ShiftNotificationStates(StatesGroup):
    """Состояния для настройки уведомлений о сменах"""
    
    # Основные настройки
    notification_main_settings = State()
    
    # Уведомления о сменах
    shift_notifications = State()
    shift_reminder_settings = State()
    
    # Уведомления о заявках
    request_notifications = State()
    request_priority_settings = State()
    
    # Экстренные уведомления
    emergency_notifications = State()
    
    # Расписание уведомлений
    notification_schedule = State()
    quiet_hours_settings = State()
    
    # Каналы уведомлений
    notification_channels = State()
    channel_preferences = State()