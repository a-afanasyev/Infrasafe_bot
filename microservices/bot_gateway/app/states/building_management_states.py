"""
Building Management FSM States.

Handles building management admin panel operations:
1. List and view buildings
2. Create new buildings in Directory
3. Edit existing building information
4. Delete buildings with confirmation

Integrates with Integration Service's Building Directory API.

P1 Priority - HIGH PRIORITY FOR ADMIN OPERATIONS
"""

from aiogram.fsm.state import State, StatesGroup


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
