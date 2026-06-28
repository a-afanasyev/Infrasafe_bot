"""FSM-состояния раздела «Контроль доступа» жителя (ТЗ §6.4, §16.2).

Бот — тонкий клиент без бизнес-логики (§4.4): состояния лишь собирают ввод для
вызова ``access_control.services.resident.*``. Две цепочки: заявка на постоянный
авто и заказ временного пропуска.
"""

from aiogram.fsm.state import State, StatesGroup


class VehicleRequestStates(StatesGroup):
    """Заявка жителя на постоянный авто: номер → тип связи → (выбор квартиры)."""

    waiting_for_plate = State()
    waiting_for_relation = State()
    waiting_for_apartment = State()


class PassOrderStates(StatesGroup):
    """Заказ временного пропуска: тип → (номер) → срок → (выбор квартиры)."""

    waiting_for_type = State()
    waiting_for_plate = State()
    waiting_for_valid_until = State()
    waiting_for_apartment = State()
