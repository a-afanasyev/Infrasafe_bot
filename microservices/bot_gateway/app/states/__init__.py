"""
FSM States Module for Bot Gateway.

Contains all Finite State Machine states for conversation flows:
- Registration: New user sign-up workflow
- Verification: Identity verification for executors
- Onboarding: New user tutorial and setup
- Profile Editing: User profile updates
- Invite Creation: Manager invite generation
- Building Selection: Building Directory integration
- Building Management: Admin building operations
- Employee Management: Manager employee operations
- Requests: Request creation and management (with building)
- Shifts: Shift assignment and management
- Admin: Administrative operations
"""

from .registration_states import RegistrationStates
from .verification_states import UserVerificationStates
from .onboarding_states import OnboardingStates
from .profile_editing_states import ProfileEditingStates
from .invite_creation_states import InviteCreationStates
from .building_selection_states import BuildingSelectionStates, RequestWithBuildingStates
from .building_management_states import BuildingManagementStates
from .employee_management_states import EmployeeManagementStates
from .request_states import *
from .shift_states import *
from .admin_states import *

__all__ = [
    # P0 Critical States (Sprint 19-22 Phase 1)
    "RegistrationStates",
    "UserVerificationStates",
    "OnboardingStates",

    # P1 High Priority States (Sprint 19-22 Phase 2)
    "ProfileEditingStates",
    "InviteCreationStates",
    "BuildingSelectionStates",
    "BuildingManagementStates",
    "EmployeeManagementStates",
    "RequestWithBuildingStates",

    # Existing States
    # Request states exported from request_states.py
    # Shift states exported from shift_states.py
    # Admin states exported from admin_states.py
]
