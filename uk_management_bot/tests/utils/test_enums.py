"""
Unit tests for utils/enums.py

Covers:
- UserRole: integer values, db_value, from_db
- Round-trip: enum → db string → enum
"""
import pytest
from uk_management_bot.utils.enums import UserRole


# ---------------------------------------------------------------------------
# UserRole
# ---------------------------------------------------------------------------

class TestUserRoleValues:
    @pytest.mark.parametrize("member, expected_int", [
        (UserRole.APPLICANT, 1),
        (UserRole.EXECUTOR, 2),
        (UserRole.MANAGER, 3),
    ])
    def test_integer_value(self, member, expected_int):
        assert int(member) == expected_int


class TestUserRoleDbValue:
    @pytest.mark.parametrize("member, expected_db", [
        (UserRole.APPLICANT, "applicant"),
        (UserRole.EXECUTOR, "executor"),
        (UserRole.MANAGER, "manager"),
    ])
    def test_db_value(self, member, expected_db):
        assert member.db_value == expected_db


class TestUserRoleFromDb:
    @pytest.mark.parametrize("member", list(UserRole))
    def test_round_trip(self, member):
        assert UserRole.from_db(member.db_value) is member

    def test_unknown_raises(self):
        with pytest.raises((KeyError, ValueError)):
            UserRole.from_db("superadmin")


# ---------------------------------------------------------------------------
# Uniqueness sanity check
# ---------------------------------------------------------------------------

class TestEnumUniqueness:
    def test_user_role_members_unique(self):
        values = [int(m) for m in UserRole]
        assert len(values) == len(set(values))
