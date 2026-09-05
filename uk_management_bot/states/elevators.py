"""FSM бота лифтёра (модуль «Лифты», Ф5, T10).

Текстовые шаги трёх сценариев карточки лифта; данные — ключи ``elvm_*``
(``elvm_elevator_id``, ``elvm_status``, ``elvm_building_id``, ``elvm_description``,
``elvm_occurrence_id``, ``elvm_kind``, ``elvm_comment``, ``elvm_cert_number``,
``elvm_cert_valid_until``). Состояние снимается ``state.clear()`` по завершении
или отмене (``elvm:cancel``).
"""

from aiogram.fsm.state import State, StatesGroup


class ElevatorStates(StatesGroup):
    """Состояния лифтёра: причина статуса, ремонт, закрытие пункта графика."""

    # Смена статуса: опциональная причина
    status_reason = State()

    # Создание ремонта: описание → срочность (inline)
    repair_description = State()
    repair_urgency = State()

    # Отметка ТО / освидетельствования выполненным
    occ_comment = State()
    cert_number = State()
    cert_valid_until = State()
    cert_url = State()
