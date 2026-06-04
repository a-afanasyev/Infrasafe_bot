"""FSM-состояния для обратной связи (жалобы / пожелания)."""

from aiogram.fsm.state import State, StatesGroup


class FeedbackStates(StatesGroup):
    waiting_for_type = State()
    waiting_for_text = State()
    waiting_for_photo = State()
    waiting_for_confirm = State()
