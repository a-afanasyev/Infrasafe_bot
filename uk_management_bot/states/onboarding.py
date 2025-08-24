"""
Состояния FSM для процесса онбординга новых пользователей

Содержит состояния для:
- Ввода телефона и адреса
- Загрузки документов
- Подтверждения данных
"""

from aiogram.fsm.state import State, StatesGroup

class OnboardingStates(StatesGroup):
    """Состояния онбординга нового пользователя"""
    
    # Базовые этапы онбординга
    waiting_for_phone = State()
    waiting_for_home_address = State()
    
    # Этапы загрузки документов
    waiting_for_document_type = State()  # Выбор типа документа
    waiting_for_document_file = State()  # Загрузка файла документа
    waiting_for_document_confirmation = State()  # Подтверждение загрузки
    
    # Завершение онбординга
    onboarding_complete = State()
