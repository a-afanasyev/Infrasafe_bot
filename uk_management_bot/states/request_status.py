"""
FSM состояния для управления статусами заявок
Определяет состояния процесса изменения статусов заявок
"""

from aiogram.fsm.state import State, StatesGroup

class RequestStatusStates(StatesGroup):
    """Состояния для управления статусами заявок"""
    
    # Состояния для выбора статуса
    waiting_for_status = State()
    
    # Состояния для ввода комментариев
    waiting_for_comment = State()
    waiting_for_materials = State()
    waiting_for_completion_report = State()
    
    # Состояния для подтверждения
    waiting_for_confirmation = State()
