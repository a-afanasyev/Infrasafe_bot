"""
Building Selection FSM States.

Handles building selection from Building Directory during:
1. Request creation
2. User verification
3. Address selection workflows

Integrates with Integration Service's Building Directory API.

P1 Priority - HIGH PRIORITY FOR BUILDING DIRECTORY INTEGRATION
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


class RequestWithBuildingStates(StatesGroup):
    """
    Enhanced Request States with Building Directory integration.

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
