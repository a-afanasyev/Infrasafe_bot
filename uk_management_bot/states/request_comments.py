"""
FSM состояния для управления комментариями к заявкам
Определяет состояния процесса добавления и просмотра комментариев
"""

from aiogram.fsm.state import State, StatesGroup

class RequestCommentStates(StatesGroup):
    """Состояния для управления комментариями к заявкам"""
    
    # Состояния для добавления комментария
    waiting_for_comment_type = State()
    waiting_for_comment = State()
    waiting_for_confirmation = State()
