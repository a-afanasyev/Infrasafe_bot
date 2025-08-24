"""
Состояния FSM для системы верификации пользователей

Содержит состояния для:
- Запроса дополнительной информации
- Управления правами доступа
- Проверки документов
"""

from aiogram.fsm.state import State, StatesGroup


class UserVerificationStates(StatesGroup):
    """Состояния для системы верификации пользователей"""
    
    # Запрос дополнительной информации
    enter_request_comment = State()  # Ввод комментария к запросу информации
    
    # Управление правами доступа
    enter_apartment_number = State()  # Ввод номера квартиры
    enter_house_number = State()      # Ввод номера дома
    enter_yard_name = State()         # Ввод названия двора
    enter_access_notes = State()      # Ввод комментариев к правам доступа
    
    # Проверка документов
    enter_document_comment = State()  # Ввод комментария к документу
    
    # Отклонение верификации
    enter_rejection_reason = State()  # Ввод причины отклонения
