"""
FSM состояния для назначения заявок
Определяет состояния процесса назначения заявок на исполнение
"""

from aiogram.fsm.state import State, StatesGroup

class RequestAssignmentStates(StatesGroup):
    """Состояния для назначения заявок"""
    
    # Состояния для выбора типа назначения
    waiting_for_assignment_type = State()
    
    # Состояния для группового назначения
    waiting_for_specialization = State()
    
    # Состояния для индивидуального назначения
    waiting_for_executor = State()
    
    # Состояния для подтверждения
    waiting_for_confirmation = State()
