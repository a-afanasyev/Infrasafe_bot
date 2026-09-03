from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """Состояния для пошаговой регистрации"""

    # Ожидание инвайт-токена после выбора «Я сотрудник» на экране /start.
    # Предшествует анкете: принятый токен переводит в waiting_for_full_name.
    waiting_for_invite_token = State()

    # «Я сотрудник» → сначала контакт (спека 2026-09-03 §3.4): телефон до
    # подтверждения анкеты живёт только в FSM-данных (employee_phone).
    waiting_for_employee_contact = State()

    # Начальное состояние - ожидание ввода ФИО
    waiting_for_full_name = State()
    
    # Ожидание ввода номера телефона
    waiting_for_phone = State()
    
    # Ожидание подтверждения должности/специализации
    waiting_for_position_confirmation = State()
    
    # Ожидание дополнительной информации (опционально)
    waiting_for_additional_info = State()
