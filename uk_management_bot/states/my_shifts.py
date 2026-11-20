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
