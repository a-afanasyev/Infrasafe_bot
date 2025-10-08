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


class RequestStatusStates(StatesGroup):
    """FSM states for request status management."""

    # Status selection
    waiting_for_status = State()

    # Comment and documentation inputs
    waiting_for_comment = State()
    waiting_for_materials = State()
    waiting_for_completion_report = State()

    # Confirmation
    waiting_for_confirmation = State()


class RequestAssignmentStates(StatesGroup):
    """FSM states for request assignment to executors."""

    # Assignment type selection
    waiting_for_assignment_type = State()

    # Group assignment (by specialization)
    waiting_for_specialization = State()

    # Individual assignment
    waiting_for_executor = State()

    # Confirmation
    waiting_for_confirmation = State()


class RequestReportStates(StatesGroup):
    """FSM states for request completion reports."""

    # Accepting completed request
    waiting_for_approval_confirmation = State()

    # Requesting revisions
    waiting_for_revision_reason = State()
