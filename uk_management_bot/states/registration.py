from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """Состояния для пошаговой регистрации"""
    
    # Начальное состояние - ожидание ввода ФИО
    waiting_for_full_name = State()
    
    # Ожидание ввода номера телефона
    waiting_for_phone = State()
    
    # Ожидание подтверждения должности/специализации
    waiting_for_position_confirmation = State()
    
    # Ожидание дополнительной информации (опционально)
    waiting_for_additional_info = State()
