"""
Request FSM States
UK Management Bot - Bot Gateway Service

FSM states for request creation and management flows.
"""

from aiogram.fsm.state import State, StatesGroup


class RequestCreationStates(StatesGroup):
    """
    Request creation flow states.

    Flow:
    1. Select building
    2. Enter apartment number
    3. Enter description
    4. Confirm creation
    """

    waiting_for_building = State()
    waiting_for_apartment = State()
    waiting_for_description = State()
    waiting_for_confirmation = State()


class RequestCommentStates(StatesGroup):
    """
    Request comment flow states.
    """

    waiting_for_comment_text = State()


class RequestCancellationStates(StatesGroup):
    """
    Request cancellation flow states.
    """

    waiting_for_cancellation_reason = State()
    waiting_for_cancellation_confirmation = State()


class RequestCompletionStates(StatesGroup):
    """
    Request completion flow states.
    """

    waiting_for_completion_comment = State()
    waiting_for_completion_confirmation = State()


class RequestReassignmentStates(StatesGroup):
    """
    Request reassignment flow states.
    """

    waiting_for_executor_selection = State()
    waiting_for_reassignment_confirmation = State()
