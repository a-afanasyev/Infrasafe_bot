"""
Unit tests for auth_helpers.py

Tests for parse_roles_safe() and get_user_roles() with various inputs.
No DB or network calls.
"""
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


# ---------------------------------------------------------------------------
# has_admin_access
# ---------------------------------------------------------------------------

class TestHasAdminAccess:
    def _make_user(self, roles=None, role=None, telegram_id=1):
        user = MagicMock()
        user.telegram_id = telegram_id
        user.roles = roles
        user.role = role
        return user

    def test_roles_list_with_manager_returns_true(self):
        from uk_management_bot.utils.auth_helpers import has_admin_access
        assert has_admin_access(roles=["manager"]) is True

    def test_roles_list_with_admin_returns_true(self):
        from uk_management_bot.utils.auth_helpers import has_admin_access
        assert has_admin_access(roles=["admin"]) is True

    def test_roles_list_applicant_only_returns_false(self):
        from uk_management_bot.utils.auth_helpers import has_admin_access
        assert has_admin_access(roles=["applicant"]) is False

    def test_no_roles_no_user_returns_false(self):
        from uk_management_bot.utils.auth_helpers import has_admin_access
        assert has_admin_access() is False

    def test_user_with_json_manager_role(self):
        from uk_management_bot.utils.auth_helpers import has_admin_access
        user = self._make_user(roles='["manager"]', role=None)
        assert has_admin_access(user=user) is True

    def test_user_with_json_executor_role_returns_false(self):
        from uk_management_bot.utils.auth_helpers import has_admin_access
        user = self._make_user(roles='["executor"]', role=None)
        assert has_admin_access(user=user) is False

    def test_user_fallback_to_role_field_admin(self):
        from uk_management_bot.utils.auth_helpers import has_admin_access
        user = self._make_user(roles=None, role="admin")
        assert has_admin_access(user=user) is True

    def test_user_fallback_to_role_field_applicant_returns_false(self):
        from uk_management_bot.utils.auth_helpers import has_admin_access
        user = self._make_user(roles=None, role="applicant")
        assert has_admin_access(user=user) is False

    def test_user_json_parse_error_falls_through(self):
        from uk_management_bot.utils.auth_helpers import has_admin_access
        user = self._make_user(roles="invalid-json-{[}", role="manager")
        # JSON parse fails, falls back to user.role == 'manager' → True
        assert has_admin_access(user=user) is True

    def test_user_roles_list_directly_not_string(self):
        from uk_management_bot.utils.auth_helpers import has_admin_access
        user = self._make_user(roles=["manager"], role=None)
        assert has_admin_access(user=user) is True


# ---------------------------------------------------------------------------
# has_executor_access
# ---------------------------------------------------------------------------

class TestHasExecutorAccess:
    def _make_user(self, roles=None, role=None, active_role=None, telegram_id=1):
        user = MagicMock()
        user.telegram_id = telegram_id
        user.roles = roles
        user.role = role
        user.active_role = active_role
        return user

    def test_roles_list_with_executor_returns_true(self):
        from uk_management_bot.utils.auth_helpers import has_executor_access
        assert has_executor_access(roles=["executor"]) is True

    def test_roles_list_applicant_returns_false(self):
        from uk_management_bot.utils.auth_helpers import has_executor_access
        assert has_executor_access(roles=["applicant"]) is False

    def test_no_roles_no_user_returns_false(self):
        from uk_management_bot.utils.auth_helpers import has_executor_access
        assert has_executor_access() is False

    def test_user_with_executor_active_role(self):
        from uk_management_bot.utils.auth_helpers import has_executor_access
        user = self._make_user(active_role="executor")
        assert has_executor_access(user=user) is True

    def test_user_with_json_executor_role(self):
        from uk_management_bot.utils.auth_helpers import has_executor_access
        user = self._make_user(roles='["executor"]', active_role=None)
        assert has_executor_access(user=user) is True

    def test_user_json_parse_error_falls_through(self):
        from uk_management_bot.utils.auth_helpers import has_executor_access
        user = self._make_user(roles="not-json", role="executor", active_role=None)
        # Falls back to user.role
        assert has_executor_access(user=user) is True

    def test_user_fallback_role_field_executor(self):
        from uk_management_bot.utils.auth_helpers import has_executor_access
        user = self._make_user(roles=None, role="executor", active_role=None)
        assert has_executor_access(user=user) is True


# ---------------------------------------------------------------------------
# get_active_role
# ---------------------------------------------------------------------------

class TestGetActiveRole:
    def _make_user(self, active_role=None, roles=None, role=None, telegram_id=1):
        user = MagicMock()
        user.telegram_id = telegram_id
        user.active_role = active_role
        user.roles = roles
        user.role = role
        return user

    def test_returns_active_role_when_set(self):
        from uk_management_bot.utils.auth_helpers import get_active_role
        user = self._make_user(active_role="executor")
        assert get_active_role(user) == "executor"

    def test_falls_back_to_first_role(self):
        from uk_management_bot.utils.auth_helpers import get_active_role
        user = self._make_user(active_role=None, roles='["manager", "applicant"]')
        result = get_active_role(user)
        assert result == "manager"

    def test_returns_applicant_when_no_roles(self):
        from uk_management_bot.utils.auth_helpers import get_active_role
        user = self._make_user(active_role=None, roles=None, role=None)
        assert get_active_role(user) == "applicant"

    def test_exception_returns_applicant(self):
        from uk_management_bot.utils.auth_helpers import get_active_role
        user = MagicMock()
        user.telegram_id = 1
        type(user).active_role = property(lambda self: (_ for _ in ()).throw(RuntimeError("err")))
        assert get_active_role(user) == "applicant"


# ---------------------------------------------------------------------------
# check_user_role (async)
# ---------------------------------------------------------------------------

import asyncio


class TestCheckUserRole:
    def _make_db_with_user(self, user=None):
        db = MagicMock()
        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = user
        return db

    def test_user_has_required_role_returns_true(self):
        from uk_management_bot.utils.auth_helpers import check_user_role
        user = MagicMock()
        user.roles = '["executor"]'
        user.role = None
        db = self._make_db_with_user(user)
        result = asyncio.get_event_loop().run_until_complete(
            check_user_role(1, "executor", db)
        )
        assert result is True

    def test_user_not_found_returns_false(self):
        from uk_management_bot.utils.auth_helpers import check_user_role
        db = self._make_db_with_user(user=None)
        result = asyncio.get_event_loop().run_until_complete(
            check_user_role(1, "manager", db)
        )
        assert result is False

    def test_db_exception_returns_false(self):
        from uk_management_bot.utils.auth_helpers import check_user_role
        db = MagicMock()
        db.query.side_effect = Exception("DB error")
        result = asyncio.get_event_loop().run_until_complete(
            check_user_role(1, "executor", db)
        )
        assert result is False
