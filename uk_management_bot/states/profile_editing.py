"""
Состояния для редактирования профиля пользователя
"""
from aiogram.fsm.state import StatesGroup, State


class ProfileEditingStates(StatesGroup):
    """Состояния для редактирования профиля"""

    # Выбор языка
    waiting_for_language_choice = State()

    # Редактирование телефона
    waiting_for_phone = State()

    # Редактирование ФИО
    waiting_for_first_name = State()
    waiting_for_last_name = State()
