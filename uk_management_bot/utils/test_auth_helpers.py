"""
Unit tests for auth_helpers.py

Tests for parse_roles_safe() and get_user_roles() with various inputs.
No DB or network calls.
"""
import pytest
from unittest.mock import MagicMock

from uk_management_bot.utils.auth_helpers import parse_roles_safe, get_user_roles


class TestParseRolesSafe:
    """Tests for parse_roles_safe()"""

    def test_json_array_input(self):
        result = parse_roles_safe('["applicant", "executor", "manager"]')
        assert result == ["applicant", "executor", "manager"]

    def test_json_single_role(self):
        result = parse_roles_safe('["executor"]')
        assert result == ["executor"]

    def test_csv_input(self):
        result = parse_roles_safe("applicant,executor,manager")
        assert result == ["applicant", "executor", "manager"]

    def test_csv_single_role(self):
        result = parse_roles_safe("manager")
        assert result == ["manager"]

    def test_csv_with_spaces(self):
        result = parse_roles_safe("applicant , executor , manager")
        assert result == ["applicant", "executor", "manager"]

    def test_none_input(self):
        result = parse_roles_safe(None)
        assert result == []

    def test_empty_string(self):
        result = parse_roles_safe("")
        assert result == []

    def test_json_empty_array(self):
        result = parse_roles_safe("[]")
        assert result == []

    def test_list_input_is_not_string_returns_empty(self):
        # parse_roles_safe expects Optional[str]; passing a list is falsy only if empty
        # A non-empty list is truthy — json.loads will fail, CSV branch checks isinstance(str)
        # So a non-empty list results in []
        result = parse_roles_safe(["applicant", "executor"])  # type: ignore[arg-type]
        assert result == []

    def test_returns_list_of_strings(self):
        result = parse_roles_safe('["applicant", "executor"]')
        assert all(isinstance(r, str) for r in result)

    def test_csv_returns_list_of_strings(self):
        result = parse_roles_safe("applicant,executor")
        assert all(isinstance(r, str) for r in result)

    def test_whitespace_only_string(self):
        result = parse_roles_safe("   ")
        # split(",") on whitespace gives ["   "], strip gives "" which is falsy
        assert result == []

    def test_csv_ignores_empty_segments(self):
        result = parse_roles_safe("applicant,,executor")
        assert result == ["applicant", "executor"]


class TestGetUserRoles:
    """Tests for get_user_roles() with mocked User objects."""

    def _make_user(self, *, roles=None, role=None, telegram_id=12345):
        user = MagicMock()
        user.telegram_id = telegram_id
        user.roles = roles
        user.role = role
        return user

    def test_json_roles_field(self):
        user = self._make_user(roles='["executor", "manager"]')
        result = get_user_roles(user)
        assert result == ["executor", "manager"]

    def test_csv_roles_field(self):
        user = self._make_user(roles="applicant,executor")
        result = get_user_roles(user)
        assert result == ["applicant", "executor"]

    def test_fallback_to_role_field_when_roles_empty(self):
        user = self._make_user(roles=None, role="manager")
        result = get_user_roles(user)
        assert result == ["manager"]

    def test_fallback_to_role_field_when_roles_empty_string(self):
        user = self._make_user(roles="", role="executor")
        result = get_user_roles(user)
        assert result == ["executor"]

    def test_default_applicant_when_both_empty(self):
        user = self._make_user(roles=None, role=None)
        result = get_user_roles(user)
        assert result == ["applicant"]

    def test_returns_list(self):
        user = self._make_user(roles='["applicant"]')
        result = get_user_roles(user)
        assert isinstance(result, list)

    def test_roles_field_takes_priority_over_role_field(self):
        user = self._make_user(roles='["manager"]', role="applicant")
        result = get_user_roles(user)
        assert result == ["manager"]

    def test_exception_returns_applicant(self):
        # Simulate attribute access raising an exception
        user = MagicMock()
        user.telegram_id = 999
        type(user).roles = property(lambda self: (_ for _ in ()).throw(RuntimeError("db error")))
        result = get_user_roles(user)
        assert result == ["applicant"]
