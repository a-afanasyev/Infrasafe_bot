"""
Bot Gateway Service - Shift Management FSM States
UK Management Bot

State definitions for shift management conversation flows.
"""

from aiogram.fsm.state import State, StatesGroup


class ShiftViewingStates(StatesGroup):
    """States for viewing shifts and schedule"""

    waiting_for_date_range = State()
    waiting_for_filter_selection = State()


class ShiftTakingStates(StatesGroup):
    """States for taking available shifts"""

    waiting_for_specialization = State()
    waiting_for_date_selection = State()
    waiting_for_shift_selection = State()
    waiting_for_confirmation = State()


class ShiftReleaseStates(StatesGroup):
    """States for releasing assigned shifts"""

    waiting_for_shift_selection = State()
    waiting_for_reason = State()
    waiting_for_confirmation = State()


class AvailabilityStates(StatesGroup):
    """States for managing availability"""

    waiting_for_action = State()  # add or remove
    waiting_for_date_from = State()
    waiting_for_date_to = State()
    waiting_for_time_range = State()
    waiting_for_recurring_choice = State()
    waiting_for_days_of_week = State()
    waiting_for_confirmation = State()


class ShiftSwapStates(StatesGroup):
    """States for shift swap requests"""

    waiting_for_shift_selection = State()
    waiting_for_executor_selection = State()
    waiting_for_confirmation = State()


class ShiftTransferStates(StatesGroup):
    """Состояния для процесса передачи смены"""

    # Инициация передачи
    select_shift = State()              # Выбор смены для передачи
    select_reason = State()             # Выбор причины передачи
    enter_comment = State()             # Ввод комментария
    select_urgency = State()            # Выбор уровня срочности
    confirm_transfer = State()          # Подтверждение передачи

    # Назначение исполнителя (для менеджеров)
    select_executor = State()           # Выбор исполнителя для назначения
    confirm_assignment = State()        # Подтверждение назначения

    # Ответ на передачу (для исполнителей)
    respond_to_transfer = State()       # Принятие/отклонение передачи
    enter_response_comment = State()    # Комментарий к ответу

    # Просмотр и управление
    view_transfers = State()            # Просмотр списка передач
    transfer_details = State()          # Детали конкретной передачи
    edit_transfer = State()             # Редактирование передачи


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
