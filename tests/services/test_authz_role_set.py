"""Инвариант набора ролей (authz/role_set) и режимы меню (catalog.is_menu_mode)."""
from uk_management_bot.authz.catalog import is_menu_mode
from uk_management_bot.authz.role_set import role_set_error


def test_engineer_requires_executor():
    assert role_set_error(["engineer"]) is not None
    assert role_set_error(["applicant", "engineer"]) is not None
    assert role_set_error(["executor", "engineer"]) is None
    assert role_set_error(["manager"]) is None


def test_capabilities_are_not_menu_modes():
    assert not is_menu_mode("engineer")
    assert not is_menu_mode("resource_meter_entry")
    assert not is_menu_mode("senior_exec")  # своя роль из админки
    assert is_menu_mode("executor") and is_menu_mode("manager")
