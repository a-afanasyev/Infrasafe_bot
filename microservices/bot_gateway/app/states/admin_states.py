"""
Bot Gateway Service - Admin FSM States
UK Management Bot

State definitions for admin panel conversation flows.
"""

from aiogram.fsm.state import State, StatesGroup


class UserManagementStates(StatesGroup):
    """States for user management"""

    waiting_for_search_query = State()
    waiting_for_user_selection = State()
    waiting_for_action = State()
    waiting_for_role_change = State()
    waiting_for_block_reason = State()
    waiting_for_confirmation = State()


class RequestManagementStates(StatesGroup):
    """States for request management (admin view)"""

    waiting_for_search_query = State()
    waiting_for_request_selection = State()
    waiting_for_action = State()
    waiting_for_reassign_executor = State()
    waiting_for_priority_change = State()
    waiting_for_status_change = State()
    waiting_for_cancellation_reason = State()
    waiting_for_confirmation = State()


class SystemConfigStates(StatesGroup):
    """States for system configuration"""

    waiting_for_config_category = State()
    waiting_for_config_parameter = State()
    waiting_for_new_value = State()
    waiting_for_confirmation = State()


class BroadcastStates(StatesGroup):
    """States for broadcast messages"""

    waiting_for_target_selection = State()  # all, role, specific users
    waiting_for_message_text = State()
    waiting_for_media = State()
    waiting_for_schedule = State()  # immediate or scheduled
    waiting_for_confirmation = State()


class AnalyticsStates(StatesGroup):
    """States for viewing analytics"""

    waiting_for_report_type = State()
    waiting_for_date_range = State()
    waiting_for_filters = State()
