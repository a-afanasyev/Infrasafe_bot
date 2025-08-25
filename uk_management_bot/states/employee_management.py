"""
FSM состояния для управления сотрудниками

Определяет состояния для:
- Ввода комментариев при модерации
- Поиска сотрудников
- Выбора специализаций и ролей
- Редактирования профиля
"""

from aiogram.fsm.state import State, StatesGroup


class EmployeeManagementStates(StatesGroup):
    """FSM состояния для управления сотрудниками"""
    
    # ═══ СОСТОЯНИЯ ДЛЯ КОММЕНТАРИЕВ ═══
    
    waiting_for_approval_comment = State()
    """Ожидание комментария для одобрения сотрудника"""
    
    waiting_for_block_reason = State()
    """Ожидание причины блокировки сотрудника"""
    
    waiting_for_unblock_comment = State()
    """Ожидание комментария для разблокировки сотрудника"""
    
    waiting_for_delete_reason = State()
    """Ожидание причины удаления сотрудника"""
    
    waiting_for_role_comment = State()
    """Ожидание комментария для изменения ролей"""
    
    waiting_for_specialization_comment = State()
    """Ожидание комментария для изменения специализаций"""
    
    # ═══ СОСТОЯНИЯ ДЛЯ ПОИСКА ═══
    
    waiting_for_search_query = State()
    """Ожидание поискового запроса"""
    
    # ═══ СОСТОЯНИЯ ДЛЯ ВЫБОРА ═══
    
    selecting_specializations = State()
    """Выбор специализаций для сотрудника"""
    
    selecting_roles = State()
    """Выбор ролей для сотрудника"""
    
    # ═══ СОСТОЯНИЯ ДЛЯ РЕДАКТИРОВАНИЯ ═══
    
    editing_full_name = State()
    """Редактирование ФИО сотрудника"""
    
    editing_phone = State()
    """Редактирование телефона сотрудника"""
    
    # ═══ СОСТОЯНИЯ ДЛЯ ПОДТВЕРЖДЕНИЯ ═══
    
    confirming_action = State()
    """Подтверждение выполнения действия"""
