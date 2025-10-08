"""
User Registration FSM States.

Handles new user registration workflow:
1. Phone number entry
2. Full name entry
3. Language selection (RU/UZ)
4. Terms & conditions acceptance
5. Account creation

P0 Priority - CRITICAL FOR NEW USERS
"""

from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """
    FSM states for new user registration workflow.

    Flow:
    1. waiting_for_phone → User enters phone number
    2. waiting_for_name → User enters full name
    3. waiting_for_language → User selects language (RU/UZ)
    4. waiting_for_terms_acceptance → User accepts terms & conditions
    5. creating_account → System creates account in User Service
    6. registration_complete → Registration successful, redirect to main menu

    Example usage:
        @router.message(RegistrationStates.waiting_for_phone)
        async def process_phone(message: Message, state: FSMContext):
            phone = message.text
            await state.update_data(phone=phone)
            await state.set_state(RegistrationStates.waiting_for_name)
    """

    # Phone number collection
    waiting_for_phone = State()

    # Full name collection
    waiting_for_name = State()

    # Language selection (RU/UZ)
    waiting_for_language = State()

    # Terms & conditions acceptance
    waiting_for_terms_acceptance = State()

    # Account creation in progress
    creating_account = State()

    # Registration complete, show onboarding
    registration_complete = State()
