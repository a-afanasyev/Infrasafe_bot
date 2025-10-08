"""
Invite Creation FSM States.

Handles invitation/invite creation workflow for managers:
1. Role selection for invite (Applicant/Executor/Manager)
2. Specialization selection (for Executor invites only)
3. Expiry period configuration
4. Confirmation before creation

P1 Priority - HIGH PRIORITY FOR MANAGER OPERATIONS
"""

from aiogram.fsm.state import State, StatesGroup


class InviteCreationStates(StatesGroup):
    """FSM states for invitation creation workflow."""

    # Role selection for the invite
    waiting_for_role = State()

    # Specialization selection (only for executor role)
    waiting_for_specialization = State()

    # Expiry period selection
    waiting_for_expiry = State()

    # Confirmation before creating the invite
    waiting_for_confirmation = State()
