"""
Profile Editing FSM States.

Handles user profile editing workflow:
1. Address editing (home, apartment, yard)
2. Language preference update
3. Phone number update
4. Name editing (first/last name)

P1 Priority - HIGH PRIORITY FOR USER EXPERIENCE
"""

from aiogram.fsm.state import State, StatesGroup


class ProfileEditingStates(StatesGroup):
    """FSM states for user profile editing workflow."""

    # Address editing states
    waiting_for_home_address = State()
    waiting_for_apartment_address = State()
    waiting_for_yard_address = State()

    # Language selection
    waiting_for_language_choice = State()

    # Phone number editing
    waiting_for_phone = State()

    # Name editing
    waiting_for_first_name = State()
    waiting_for_last_name = State()
