"""Smoke tests: verify all handler modules import cleanly and export routers."""
import pytest
from aiogram import Router


# List ALL handler files — includes shift_transfer and user_verification
# which are present in the codebase but not in the original spec list.
HANDLER_MODULES = [
    "uk_management_bot.handlers.base",
    "uk_management_bot.handlers.requests",
    "uk_management_bot.handlers.admin",
    "uk_management_bot.handlers.shifts",
    "uk_management_bot.handlers.auth",
    "uk_management_bot.handlers.onboarding",
    "uk_management_bot.handlers.my_shifts",
    "uk_management_bot.handlers.profile_editing",
    "uk_management_bot.handlers.health",
    "uk_management_bot.handlers.employee_management",
    "uk_management_bot.handlers.request_acceptance",
    "uk_management_bot.handlers.request_assignment",
    "uk_management_bot.handlers.request_comments",
    "uk_management_bot.handlers.request_reports",
    "uk_management_bot.handlers.request_status_management",
    "uk_management_bot.handlers.shift_management",
    "uk_management_bot.handlers.clarification_replies",
    "uk_management_bot.handlers.unaccepted_requests",
    "uk_management_bot.handlers.address_yards",
    "uk_management_bot.handlers.address_buildings",
    "uk_management_bot.handlers.address_apartments",
    "uk_management_bot.handlers.address_moderation",
    "uk_management_bot.handlers.user_management",
    "uk_management_bot.handlers.user_apartments",
    "uk_management_bot.handlers.user_apartment_selection",
    "uk_management_bot.handlers.user_yards_management",
    # Extra modules present in the codebase
    "uk_management_bot.handlers.shift_transfer",
    "uk_management_bot.handlers.user_verification",
]


class TestHandlerImports:
    @pytest.mark.parametrize("module_name", HANDLER_MODULES)
    def test_module_imports(self, module_name):
        """Each handler module should import without errors."""
        import importlib
        mod = importlib.import_module(module_name)
        assert mod is not None

    @pytest.mark.parametrize("module_name", HANDLER_MODULES)
    def test_module_has_router(self, module_name):
        """Each handler module should export a Router instance."""
        import importlib
        mod = importlib.import_module(module_name)
        router = getattr(mod, "router", None) or getattr(mod, "start_router", None)
        assert router is not None, f"{module_name} has no 'router' or 'start_router' attribute"
        assert isinstance(router, Router), (
            f"{module_name}.router is not a Router instance (got {type(router).__name__})"
        )
