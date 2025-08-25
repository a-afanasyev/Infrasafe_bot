"""
Состояния для создания приглашений (инвайтов)
"""
from aiogram.fsm.state import State, StatesGroup

class InviteCreationStates(StatesGroup):
    """Состояния создания приглашения"""
    
    # Выбор роли для приглашения
    waiting_for_role = State()
    
    # Выбор специализации (только для executor)
    waiting_for_specialization = State()
    
    # Выбор срока действия приглашения
    waiting_for_expiry = State()
    
    # Подтверждение создания приглашения
    waiting_for_confirmation = State()
