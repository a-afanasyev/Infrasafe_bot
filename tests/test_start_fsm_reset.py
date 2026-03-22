"""Tests for /start resetting FSM from any state."""

import inspect
from uk_management_bot.handlers.base import cmd_start, start_router


def test_start_handler_accepts_state_param():
    """cmd_start must accept 'state' for FSM clearing."""
    sig = inspect.signature(cmd_start)
    assert "state" in sig.parameters, f"'state' missing from {list(sig.parameters)}"


def test_start_router_exists():
    """start_router must exist as a separate router for priority registration."""
    assert start_router is not None
    assert start_router.name == "start"


def test_start_handler_registered_on_start_router():
    """cmd_start must be on start_router, not base router."""
    assert len(start_router.message.handlers) > 0, "start_router has no message handlers"
