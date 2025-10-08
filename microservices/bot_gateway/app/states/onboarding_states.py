"""
User Onboarding FSM States.

Handles onboarding workflow for new users:
1. Welcome tour
2. Feature introduction
3. Role selection (Applicant/Executor)
4. Profile setup
5. Tutorial completion

P0 Priority - CRITICAL FOR USER EXPERIENCE
"""

from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    """
    FSM states for new user onboarding workflow.

    Flow:
    1. welcome_tour → Show welcome message and bot features
    2. feature_introduction → Introduce main features (requests, shifts, etc.)
    3. role_selection → User selects primary role (Applicant/Executor)
    4. profile_setup → User fills basic profile information
    5. specialization_selection → Executor selects specializations (if executor)
    6. building_selection → User selects buildings/districts (if executor)
    7. tutorial_start → Start interactive tutorial
    8. tutorial_complete → Onboarding complete, redirect to main menu

    Example usage:
        @router.message(OnboardingStates.role_selection)
        async def process_role(message: Message, state: FSMContext):
            role = message.text
            await state.update_data(role=role)

            if role == "Executor":
                await state.set_state(OnboardingStates.specialization_selection)
            else:
                await state.set_state(OnboardingStates.tutorial_start)
    """

    # Welcome tour
    welcome_tour = State()

    # Feature introduction
    feature_introduction = State()

    # Role selection (Applicant/Executor/Manager)
    role_selection = State()

    # Profile setup
    profile_setup = State()

    # Specialization selection (for Executors)
    specialization_selection = State()

    # Building/district selection (for Executors)
    building_selection = State()

    # Work schedule setup (for Executors)
    schedule_setup = State()

    # Tutorial start
    tutorial_start = State()

    # Interactive tutorial in progress
    tutorial_in_progress = State()

    # Tutorial complete
    tutorial_complete = State()

    # Onboarding complete, redirect to main menu
    onboarding_complete = State()
