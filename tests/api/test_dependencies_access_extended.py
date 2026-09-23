"""Tests for is_assigned_executor
(uk_management_bot/api/dependencies_access.py).

The check_request_access tests live in test_dependencies_access.py (inline).
This file covers is_assigned_executor (sync).
"""
from unittest.mock import MagicMock

from uk_management_bot.api.dependencies_access import is_assigned_executor


# ═══════════════════════ is_assigned_executor ═══════════════════════


class TestIsAssignedExecutor:

    def _make_request(self, executor_id=None):
        req = MagicMock()
        req.executor_id = executor_id
        return req

    def _make_user(self, user_id: int):
        user = MagicMock()
        user.id = user_id
        return user

    def _make_assignment(self, executor_id: int, status: str = "active"):
        a = MagicMock()
        a.executor_id = executor_id
        a.status = status
        return a

    def test_matched_by_executor_id(self):
        req = self._make_request(executor_id=42)
        user = self._make_user(42)
        assert is_assigned_executor(req, user, []) is True

    def test_not_matched_by_executor_id(self):
        req = self._make_request(executor_id=99)
        user = self._make_user(42)
        assert is_assigned_executor(req, user, []) is False

    def test_matched_by_active_assignment(self):
        req = self._make_request(executor_id=None)
        user = self._make_user(42)
        assignments = [self._make_assignment(42, "active")]
        assert is_assigned_executor(req, user, assignments) is True

    def test_not_matched_by_inactive_assignment(self):
        req = self._make_request(executor_id=None)
        user = self._make_user(42)
        assignments = [self._make_assignment(42, "completed")]
        assert is_assigned_executor(req, user, assignments) is False

    def test_not_matched_by_other_executor_assignment(self):
        req = self._make_request(executor_id=None)
        user = self._make_user(42)
        assignments = [self._make_assignment(99, "active")]
        assert is_assigned_executor(req, user, assignments) is False

    def test_empty_assignments(self):
        req = self._make_request(executor_id=None)
        user = self._make_user(42)
        assert is_assigned_executor(req, user, []) is False

    def test_executor_id_takes_priority(self):
        """If executor_id matches, assignments are not checked."""
        req = self._make_request(executor_id=42)
        user = self._make_user(42)
        # Even with no assignments, should return True
        assert is_assigned_executor(req, user, []) is True

    def test_multiple_assignments_one_active(self):
        req = self._make_request(executor_id=None)
        user = self._make_user(42)
        assignments = [
            self._make_assignment(42, "completed"),
            self._make_assignment(42, "active"),
        ]
        assert is_assigned_executor(req, user, assignments) is True

