"""FSM-состояния списания материалов исполнителем на заявку (складской учёт)."""
from aiogram.fsm.state import State, StatesGroup


class MaterialIssueStates(StatesGroup):
    """Сценарий: выбор материала → ввод количества → подтверждение."""

    selecting_material = State()
    entering_quantity = State()
    confirming = State()
