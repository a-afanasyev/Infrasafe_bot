"""
FSM состояния для управления отчетами о выполнении заявок
Определяет состояния процесса принятия и доработки заявок
"""

from aiogram.fsm.state import State, StatesGroup

class RequestReportStates(StatesGroup):
    """Состояния для управления отчетами о выполнении заявок"""
    
    # Состояния для принятия заявки
    waiting_for_approval_confirmation = State()
    
    # Состояния для запроса доработки
    waiting_for_revision_reason = State()
