"""
Bot Gateway Service - Shift Management FSM States
UK Management Bot

State definitions for shift management conversation flows.
"""

from aiogram.fsm.state import State, StatesGroup


class ShiftViewingStates(StatesGroup):
    """States for viewing shifts and schedule"""

    waiting_for_date_range = State()
    waiting_for_filter_selection = State()


class ShiftTakingStates(StatesGroup):
    """States for taking available shifts"""

    waiting_for_specialization = State()
    waiting_for_date_selection = State()
    waiting_for_shift_selection = State()
    waiting_for_confirmation = State()


class ShiftReleaseStates(StatesGroup):
    """States for releasing assigned shifts"""

    waiting_for_shift_selection = State()
    waiting_for_reason = State()
    waiting_for_confirmation = State()


class AvailabilityStates(StatesGroup):
    """States for managing availability"""

    waiting_for_action = State()  # add or remove
    waiting_for_date_from = State()
    waiting_for_date_to = State()
    waiting_for_time_range = State()
    waiting_for_recurring_choice = State()
    waiting_for_days_of_week = State()
    waiting_for_confirmation = State()


class ShiftSwapStates(StatesGroup):
    """States for shift swap requests"""

    waiting_for_shift_selection = State()
    waiting_for_executor_selection = State()
    waiting_for_confirmation = State()
