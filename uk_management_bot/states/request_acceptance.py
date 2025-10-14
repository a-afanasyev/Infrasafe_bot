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

    viewing_completed_requests = State()  # Просмотр списка исполненных заявок
    viewing_completed_request_details = State()  # Просмотр деталей исполненной заявки
    awaiting_confirmation_notes = State()  # Ожидание комментариев при подтверждении
    awaiting_return_to_work_reason = State()  # Ожидание причины возврата в работу


class ApplicantAcceptanceStates(StatesGroup):
    """Состояния заявителя при приёмке выполненных заявок"""

    viewing_pending_acceptance = State()  # Просмотр списка заявок, ожидающих приёмки
    viewing_completed_request = State()  # Просмотр деталей выполненной заявки
    viewing_completion_media = State()  # Просмотр медиа выполненной заявки
    selecting_rating = State()  # Выбор оценки (1-5 звёзд)
    awaiting_return_reason = State()  # Ожидание причины возврата заявки
    awaiting_return_media = State()  # Ожидание медиафайлов при возврате (опционально)
