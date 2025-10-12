"""Building Selection FSM States.

Week 2, Task 5.1: FSM States for Building Directory Integration
States for building selection during request creation and verification.
"""

from aiogram.fsm.state import State, StatesGroup


class BuildingSelectionStates(StatesGroup):
    """States for building selection from Directory."""

    # City selection
    selecting_city = State()  # User selects city from list

    # Building search/selection
    searching_building = State()  # User searches for building (street/house)
    selecting_building = State()  # User selects building from search results
    viewing_building_details = State()  # User views building details

    # Manual address input (fallback)
    entering_manual_address = State()  # User enters address manually if building not found


class BuildingManagementStates(StatesGroup):
    """States for building management (admin panel)."""

    # List and view
    viewing_buildings = State()  # Admin views building list
    viewing_building_info = State()  # Admin views specific building

    # Create building
    creating_building_city = State()  # Enter city
    creating_building_street = State()  # Enter street
    creating_building_house = State()  # Enter house number
    creating_building_corpus = State()  # Enter corpus (optional)
    creating_building_details = State()  # Enter additional details
    creating_building_confirm = State()  # Confirm creation

    # Edit building
    editing_building_select_field = State()  # Select field to edit
    editing_building_enter_value = State()  # Enter new value
    editing_building_confirm = State()  # Confirm edit

    # Delete building
    deleting_building_confirm = State()  # Confirm deletion


class RequestWithBuildingStates(StatesGroup):
    """Enhanced Request States with Building Directory integration.

    This extends the existing RequestStates flow with building selection.
    """

    # Category selection (existing)
    category = State()

    # NEW: Building selection (replaces/enhances address)
    building_selection_city = State()  # Select city
    building_selection_search = State()  # Search building by street/house
    building_selection_choose = State()  # Choose from search results
    building_selection_confirm = State()  # Confirm selected building

    # Address details (apartment/entrance/floor)
    address_details = State()  # Enter apartment, entrance, floor (optional)

    # Rest of the flow (existing)
    description = State()
    urgency = State()
    media = State()
    confirm = State()
    waiting_clarify_reply = State()
