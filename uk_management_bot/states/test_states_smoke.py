"""
Smoke tests for all FSM state modules.

Tests that:
- Each state module imports without error
- Each StatesGroup subclass has at least one State() attribute
"""
import importlib
import inspect
import pytest
from aiogram.fsm.state import State, StatesGroup


# ---------------------------------------------------------------------------
# Enumerate all state modules (read from the states/ directory)
# ---------------------------------------------------------------------------

STATE_MODULES = [
    "uk_management_bot.states.address_management",
    "uk_management_bot.states.employee_management",
    "uk_management_bot.states.invite_creation",
    "uk_management_bot.states.my_shifts",
    "uk_management_bot.states.onboarding",
    "uk_management_bot.states.profile_editing",
    "uk_management_bot.states.registration",
    "uk_management_bot.states.request_acceptance",
    "uk_management_bot.states.request_assignment",
    "uk_management_bot.states.request_comments",
    "uk_management_bot.states.request_reports",
    "uk_management_bot.states.request_status",
    "uk_management_bot.states.shift_management",
    "uk_management_bot.states.shift_transfer",
    "uk_management_bot.states.user_management",
    "uk_management_bot.states.user_verification",
]


def _collect_states_groups(module) -> list:
    """Return all StatesGroup subclasses defined in *module*."""
    result = []
    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, StatesGroup) and obj is not StatesGroup:
            result.append(obj)
    return result


def _collect_state_attrs(group_cls) -> list:
    """Return all State instances that are class-level attributes of *group_cls*."""
    states = []
    for attr_name in dir(group_cls):
        if attr_name.startswith("_"):
            continue
        try:
            val = getattr(group_cls, attr_name)
        except Exception:
            continue
        if isinstance(val, State):
            states.append(attr_name)
    return states


# ---------------------------------------------------------------------------
# Parametrize over module names
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("module_path", STATE_MODULES)
class TestStatesModuleSmoke:
    def test_imports_without_error(self, module_path: str):
        """The module must be importable without raising any exception."""
        module = importlib.import_module(module_path)
        assert module is not None

    def test_contains_at_least_one_states_group(self, module_path: str):
        """Each state module must define at least one StatesGroup subclass."""
        module = importlib.import_module(module_path)
        groups = _collect_states_groups(module)
        assert len(groups) >= 1, (
            f"{module_path} does not define any StatesGroup subclass"
        )

    def test_states_groups_have_state_attributes(self, module_path: str):
        """Every StatesGroup subclass in the module must have at least one State() attribute."""
        module = importlib.import_module(module_path)
        groups = _collect_states_groups(module)
        for group_cls in groups:
            states = _collect_state_attrs(group_cls)
            assert len(states) >= 1, (
                f"{group_cls.__name__} in {module_path} has no State() attributes"
            )
