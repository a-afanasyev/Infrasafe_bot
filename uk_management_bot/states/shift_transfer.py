"""
Состояния для обработки передачи смен между исполнителями
"""

from aiogram.fsm.state import State, StatesGroup


class ShiftTransferStates(StatesGroup):
    """Состояния для процесса передачи смены"""

    # Инициация передачи
    select_shift = State()              # Выбор смены для передачи
    select_reason = State()             # Выбор причины передачи
    enter_comment = State()             # Ввод комментария
    select_urgency = State()            # Выбор уровня срочности
    confirm_transfer = State()          # Подтверждение передачи
