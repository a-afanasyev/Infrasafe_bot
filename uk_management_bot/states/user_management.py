"""
FSM состояния для управления пользователями

Определяет состояния для:
- Ввода комментариев при модерации
- Поиска пользователей
- Выбора специализаций и ролей
"""

from aiogram.fsm.state import State, StatesGroup


class UserManagementStates(StatesGroup):
    """FSM состояния для управления пользователями"""
    
    # ═══ СОСТОЯНИЯ ДЛЯ КОММЕНТАРИЕВ ═══
    
    waiting_for_approval_comment = State()
    """Ожидание комментария для одобрения пользователя"""
    
    waiting_for_block_reason = State()
    """Ожидание причины блокировки пользователя"""
    
    waiting_for_unblock_comment = State()
    """Ожидание комментария для разблокировки пользователя"""
    
    waiting_for_role_comment = State()
    """Ожидание комментария для изменения ролей"""
    
    waiting_for_specialization_comment = State()
    """Ожидание комментария для изменения специализаций"""
    
    # ═══ СОСТОЯНИЯ ДЛЯ ПОИСКА ═══
    
    waiting_for_search_query = State()
    """Ожидание поискового запроса"""
    
    waiting_for_search_filters = State()
    """Настройка фильтров поиска"""
    
    # ═══ СОСТОЯНИЯ ДЛЯ ВЫБОРА ═══
    
    selecting_specializations = State()
    """Выбор специализаций для исполнителя"""
    
    selecting_roles = State()
    """Выбор ролей для пользователя"""
    
    # ═══ СОСТОЯНИЯ ДЛЯ ПОДТВЕРЖДЕНИЯ ═══
    
    confirming_action = State()
    """Подтверждение выполнения действия"""
