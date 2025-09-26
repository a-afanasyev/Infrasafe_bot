from aiogram.fsm.state import State, StatesGroup


class QuarterlyPlanningStates(StatesGroup):
    """FSM состояния для квартального планирования смен."""
    
    # Основной процесс планирования
    selecting_quarter = State()           # Выбор квартала для планирования
    selecting_specializations = State()   # Выбор специализаций
    configuring_settings = State()        # Настройка дополнительных параметров
    confirming_plan = State()             # Подтверждение создания плана
    executing_plan = State()              # Выполнение планирования
    viewing_results = State()             # Просмотр результатов
    
    # Управление существующими планами
    browsing_plans = State()              # Просмотр существующих планов
    editing_plan = State()                # Редактирование плана
    adjusting_assignments = State()       # Корректировка назначений
    
    # Разрешение конфликтов
    reviewing_conflicts = State()         # Просмотр конфликтов
    resolving_conflict = State()          # Разрешение конкретного конфликта
    selecting_resolution = State()        # Выбор способа разрешения
    
    # Управление передачами
    viewing_transfers = State()           # Просмотр передач смен
    initiating_transfer = State()         # Инициация передачи
    configuring_transfer = State()        # Настройка передачи
    monitoring_transfer = State()         # Мониторинг передачи
    
    # Статистика и аналитика
    viewing_statistics = State()          # Просмотр статистики
    configuring_report = State()          # Настройка отчета
    exporting_data = State()              # Экспорт данных
    
    # Настройки системы
    advanced_settings = State()           # Дополнительные настройки
    calendar_management = State()         # Управление календарем
    work_hours_config = State()           # Настройка рабочих часов
    notification_config = State()         # Настройка уведомлений
    
    # Вспомогательные состояния
    waiting_input = State()               # Ожидание ввода от пользователя
    processing = State()                  # Обработка данных
    error_handling = State()              # Обработка ошибок