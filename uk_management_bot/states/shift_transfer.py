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