"""Unit tests for _parse_user_roles() in uk_management_bot/api/dependencies.py."""
from unittest.mock import MagicMock

from uk_management_bot.api.dependencies import _parse_user_roles


class TestParseUserRoles:
    def test_json_array_string(self):
        """JSON-encoded list is decoded to a Python list."""
        user = MagicMock()
        user.roles = '["applicant","executor"]'
        result = _parse_user_roles(user)
        assert result == ["applicant", "executor"]

    def test_json_array_with_whitespace(self):
        """Whitespace around the JSON string is stripped before parsing."""
        user = MagicMock()
        user.roles = '  ["manager"]  '
        result = _parse_user_roles(user)
        assert result == ["manager"]

    def test_csv_string(self):
        """Comma-separated string is split into a list."""
        user = MagicMock()
        user.roles = "applicant,executor"
        result = _parse_user_roles(user)
        assert result == ["applicant", "executor"]

    def test_csv_string_with_spaces(self):
        """Spaces around CSV items are stripped."""
        user = MagicMock()
        user.roles = " applicant , executor "
        result = _parse_user_roles(user)
        assert result == ["applicant", "executor"]

    def test_single_role_string(self):
        """A single non-JSON string becomes a one-element list."""
        user = MagicMock()
        user.roles = "manager"
        result = _parse_user_roles(user)
        assert result == ["manager"]

    def test_empty_roles_falls_back_to_active_role(self):
        """PR-31/DB-060: legacy .role dropped — empty roles falls back via
        legacy_primary_role() to user.active_role."""
        user = MagicMock()
        user.roles = ""
        user.active_role = "applicant"
        result = _parse_user_roles(user)
        assert result == ["applicant"]

    def test_none_roles_falls_back_to_active_role(self):
        """PR-31/DB-060: None roles falls back to user.active_role."""
        user = MagicMock()
        user.roles = None
        user.active_role = "executor"
        result = _parse_user_roles(user)
        assert result == ["executor"]

    def test_none_roles_none_active_role_returns_empty(self):
        """Both roles and active_role are None/falsy — returns empty list."""
        user = MagicMock()
        user.roles = None
        user.active_role = None
        result = _parse_user_roles(user)
        assert result == []

    def test_empty_roles_no_active_role_returns_empty(self):
        """Empty roles string and no active_role returns empty list."""
        user = MagicMock()
        user.roles = ""
        user.active_role = ""
        result = _parse_user_roles(user)
        assert result == []

    def test_invalid_json_falls_back_to_csv(self):
        """Malformed JSON starting with '[' falls back to CSV splitting."""
        user = MagicMock()
        # Starts with '[' but is not valid JSON — falls through to CSV split
        user.roles = "[not-valid-json"
        result = _parse_user_roles(user)
        # CSV split on a string starting with '[' — the value is kept as-is
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_non_string_json_items_are_dropped(self):
        """NICE-078: parsing is delegated to parse_roles_safe, which DROPS
        non-string items (a role is always a string — numeric garbage must not
        be coerced into a bogus role like "1")."""
        user = MagicMock()
        user.roles = '["manager", 1, 2]'
        result = _parse_user_roles(user)
        assert result == ["manager"]
