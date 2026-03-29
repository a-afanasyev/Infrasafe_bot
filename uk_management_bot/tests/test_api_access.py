"""Unit tests for API access control dependencies."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uk_management_bot.api.dependencies_access import (
    is_assigned_executor,
)


class TestIsAssignedExecutor:
    def test_executor_id_match(self):
        """Executor matched by request.executor_id (legacy fallback)."""
        request = MagicMock(executor_id=42)
        user = MagicMock(id=42)
        assert is_assigned_executor(request, user, []) is True

    def test_executor_id_no_match(self):
        """Executor not matched by executor_id."""
        request = MagicMock(executor_id=99)
        user = MagicMock(id=42)
        assert is_assigned_executor(request, user, []) is False

    def test_assignment_match(self):
        """Executor matched via RequestAssignment."""
        request = MagicMock(executor_id=None)
        user = MagicMock(id=42)
        assignment = MagicMock(executor_id=42, status="active")
        assert is_assigned_executor(request, user, [assignment]) is True

    def test_assignment_inactive(self):
        """Inactive assignment does not match."""
        request = MagicMock(executor_id=None)
        user = MagicMock(id=42)
        assignment = MagicMock(executor_id=42, status="revoked")
        assert is_assigned_executor(request, user, [assignment]) is False

    def test_no_match(self):
        """No executor_id and no assignment — no access."""
        request = MagicMock(executor_id=None)
        user = MagicMock(id=42)
        other_assignment = MagicMock(executor_id=99, status="active")
        assert is_assigned_executor(request, user, [other_assignment]) is False

    def test_combined_fallback(self):
        """executor_id match even when assignments don't match."""
        request = MagicMock(executor_id=42)
        user = MagicMock(id=42)
        other_assignment = MagicMock(executor_id=99, status="active")
        assert is_assigned_executor(request, user, [other_assignment]) is True
