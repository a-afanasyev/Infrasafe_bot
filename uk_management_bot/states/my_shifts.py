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

