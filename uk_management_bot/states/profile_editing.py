"""
Состояния для редактирования профиля пользователя
"""
from aiogram.fsm.state import StatesGroup, State


class ProfileEditingStates(StatesGroup):
    """Состояния для редактирования профиля"""
    
    # Редактирование адреса
    waiting_for_home_address = State()
    waiting_for_apartment_address = State()
    waiting_for_yard_address = State()
    
    # Выбор языка
    waiting_for_language_choice = State()
    
    # Редактирование телефона
    waiting_for_phone = State()
    
    # Редактирование ФИО
    waiting_for_first_name = State()
    waiting_for_last_name = State()
