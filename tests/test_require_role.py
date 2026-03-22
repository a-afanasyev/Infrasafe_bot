"""Tests for require_role decorator preserving function signature."""

import inspect
import asyncio
from unittest.mock import AsyncMock, MagicMock
from uk_management_bot.middlewares.auth import require_role


def test_decorator_preserves_parameter_names():
    """After decoration, aiogram must see the original parameter names."""

    @require_role(["executor"])
    async def my_handler(message, db, roles, user, language: str = "ru"):
        pass

    sig = inspect.signature(my_handler)
    param_names = list(sig.parameters.keys())
    assert "db" in param_names, f"'db' missing from {param_names}"
    assert "roles" in param_names, f"'roles' missing from {param_names}"
    assert "user" in param_names, f"'user' missing from {param_names}"
    assert "language" in param_names, f"'language' missing from {param_names}"


def test_decorator_preserves_defaults():
    """Default values must be preserved for DI."""

    @require_role(["manager"])
    async def my_handler(callback, db: "Session" = None, roles: list = None,
                         active_role: str = None, user=None, language: str = "ru"):
        pass

    sig = inspect.signature(my_handler)
    assert sig.parameters["language"].default == "ru"
    assert sig.parameters["roles"].default is None


def test_decorator_blocks_unauthorized():
    """Handler should not execute if user lacks required role."""
    executed = False

    @require_role(["admin"])
    async def my_handler(message, db=None, roles=None, user=None, language="ru"):
        nonlocal executed
        executed = True

    mock_msg = MagicMock()
    mock_msg.from_user = MagicMock(id=123)
    mock_msg.answer = AsyncMock()

    asyncio.run(
        my_handler(mock_msg, db=None, roles=["executor"], user=None, language="ru")
    )
    assert not executed, "Handler ran despite missing role"


def test_decorator_allows_authorized():
    """Handler should execute if user has required role."""
    executed = False

    @require_role(["executor"])
    async def my_handler(message, db=None, roles=None, user=None, language="ru"):
        nonlocal executed
        executed = True
        return "ok"

    mock_msg = MagicMock()
    mock_msg.from_user = MagicMock(id=123)

    result = asyncio.run(
        my_handler(mock_msg, db=None, roles=["executor"], user=None, language="ru")
    )
    assert executed
    assert result == "ok"
