"""
Employee Management FSM States.

Handles employee/user management workflows for managers:
1. Comment collection during moderation
2. Employee search
3. Specialization and role selection
4. Profile editing for employees
5. Action confirmations

P1 Priority - HIGH PRIORITY FOR MANAGER OPERATIONS
"""

from aiogram.fsm.state import State, StatesGroup


class EmployeeManagementStates(StatesGroup):
    """FSM states for employee management workflows."""

    # ═══ COMMENT STATES ═══

    waiting_for_approval_comment = State()
    """Waiting for approval comment when approving an employee"""

    waiting_for_block_reason = State()
    """Waiting for block reason when blocking an employee"""

    waiting_for_unblock_comment = State()
    """Waiting for comment when unblocking an employee"""

    waiting_for_delete_reason = State()
    """Waiting for reason when deleting an employee"""

    waiting_for_role_comment = State()
    """Waiting for comment when changing employee roles"""

    waiting_for_specialization_comment = State()
    """Waiting for comment when changing employee specializations"""

    # ═══ SEARCH STATES ═══

    waiting_for_search_query = State()
    """Waiting for search query to find employees"""

    # ═══ SELECTION STATES ═══

    selecting_specializations = State()
    """Selecting specializations for an employee"""

    selecting_roles = State()
    """Selecting roles for an employee"""

    # ═══ EDITING STATES ═══

    editing_full_name = State()
    """Editing employee full name"""

    editing_phone = State()
    """Editing employee phone number"""

    # ═══ CONFIRMATION STATES ═══

    confirming_action = State()
    """Confirming action execution"""
