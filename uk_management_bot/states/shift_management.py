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

    # Планирование смен
    selecting_template = State()
    selecting_date = State()

    # Просмотр расписания
    viewing_schedule = State()

    # Автоматическое планирование
    auto_planning_settings = State()

    # Управление шаблонами
    template_name_input = State()
    template_time_input = State()
    template_duration_input = State()
    template_specialization_selection = State()


class TemplateManagementStates(StatesGroup):
    """Состояния для управления шаблонами смен"""

    # Редактирование шаблона
    editing_template = State()
    editing_field = State()


class ExecutorAssignmentStates(StatesGroup):
    """Состояния для назначения исполнителей на смены"""

    # Выбор исполнителя
    viewing_available_executors = State()
