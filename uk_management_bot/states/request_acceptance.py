"""
FSM состояния для процесса приёмки выполненных заявок

Включает состояния для:
- Подтверждения менеджером
- Приёмки заявителем с оценкой
- Возврата заявки заявителем
"""

from aiogram.fsm.state import State, StatesGroup


class ManagerAcceptanceStates(StatesGroup):
    """Состояния менеджера при работе с исполненными заявками"""

    awaiting_return_to_work_reason = State()  # Ожидание причины возврата в работу
    awaiting_manager_acceptance_comment = State()  # Ожидание комментария при принятии за заявителя


class ApplicantAcceptanceStates(StatesGroup):
    """Состояния заявителя при приёмке выполненных заявок"""

    awaiting_return_reason = State()  # Ожидание причины возврата заявки
    awaiting_return_media = State()  # Ожидание медиафайлов при возврате (опционально)
