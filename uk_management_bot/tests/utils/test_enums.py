"""
Unit tests for utils/enums.py

Covers:
- RequestStatus: integer values, db_value, locale_key, from_db, from_db_safe
- ShiftStatus: integer values, db_value, from_db
- UserRole: integer values, db_value, from_db
- Round-trip: enum → db string → enum
"""
import pytest
from uk_management_bot.utils.enums import RequestStatus, ShiftStatus, UserRole


# ---------------------------------------------------------------------------
# RequestStatus
# ---------------------------------------------------------------------------

class TestRequestStatusValues:
    """Each member has the correct integer value."""

    @pytest.mark.parametrize("member, expected_int", [
        (RequestStatus.NEW, 1),
        (RequestStatus.IN_PROGRESS, 2),
        (RequestStatus.PURCHASE, 3),
        (RequestStatus.CLARIFICATION, 4),
        (RequestStatus.EXECUTED, 5),
        (RequestStatus.COMPLETED, 6),
        (RequestStatus.APPROVED, 7),
        (RequestStatus.CANCELLED, 8),
    ])
    def test_integer_value(self, member, expected_int):
        assert int(member) == expected_int


class TestRequestStatusDbValue:
    """db_value property returns the expected Russian string."""

    @pytest.mark.parametrize("member, expected_db", [
        (RequestStatus.NEW, "Новая"),
        (RequestStatus.IN_PROGRESS, "В работе"),
        (RequestStatus.PURCHASE, "Закуп"),
        (RequestStatus.CLARIFICATION, "Уточнение"),
        (RequestStatus.EXECUTED, "Выполнена"),
        (RequestStatus.COMPLETED, "Исполнено"),
        (RequestStatus.APPROVED, "Принято"),
        (RequestStatus.CANCELLED, "Отменена"),
    ])
    def test_db_value(self, member, expected_db):
        assert member.db_value == expected_db


class TestRequestStatusLocaleKey:
    """locale_key property starts with 'statuses.'."""

    @pytest.mark.parametrize("member", list(RequestStatus))
    def test_locale_key_format(self, member):
        assert member.locale_key.startswith("statuses.")


class TestRequestStatusFromDb:
    """from_db() round-trip."""

    @pytest.mark.parametrize("member", list(RequestStatus))
    def test_round_trip(self, member):
        assert RequestStatus.from_db(member.db_value) is member

    def test_unknown_raises_key_error(self):
        with pytest.raises((KeyError, ValueError)):
            RequestStatus.from_db("НеизвестноеЗначение")


class TestRequestStatusFromDbSafe:
    def test_valid_returns_member(self):
        result = RequestStatus.from_db_safe("Новая")
        assert result is RequestStatus.NEW

    def test_unknown_returns_default_none(self):
        result = RequestStatus.from_db_safe("unknown")
        assert result is None

    def test_unknown_with_custom_default(self):
        result = RequestStatus.from_db_safe("unknown", default=RequestStatus.CANCELLED)
        assert result is RequestStatus.CANCELLED


# ---------------------------------------------------------------------------
# ShiftStatus
# ---------------------------------------------------------------------------

class TestShiftStatusValues:
    @pytest.mark.parametrize("member, expected_int", [
        (ShiftStatus.ACTIVE, 1),
        (ShiftStatus.COMPLETED, 2),
        (ShiftStatus.CANCELLED, 3),
        (ShiftStatus.PLANNED, 4),
        (ShiftStatus.PAUSED, 5),
    ])
    def test_integer_value(self, member, expected_int):
        assert int(member) == expected_int


class TestShiftStatusDbValue:
    @pytest.mark.parametrize("member, expected_db", [
        (ShiftStatus.ACTIVE, "active"),
        (ShiftStatus.COMPLETED, "completed"),
        (ShiftStatus.CANCELLED, "cancelled"),
        (ShiftStatus.PLANNED, "planned"),
        (ShiftStatus.PAUSED, "paused"),
    ])
    def test_db_value(self, member, expected_db):
        assert member.db_value == expected_db


class TestShiftStatusFromDb:
    @pytest.mark.parametrize("member", list(ShiftStatus))
    def test_round_trip(self, member):
        assert ShiftStatus.from_db(member.db_value) is member

    def test_unknown_raises(self):
        with pytest.raises((KeyError, ValueError)):
            ShiftStatus.from_db("nonexistent")


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
# Cross-enum uniqueness sanity checks
# ---------------------------------------------------------------------------

class TestEnumUniqueness:
    def test_request_status_members_unique(self):
        values = [int(m) for m in RequestStatus]
        assert len(values) == len(set(values))

    def test_shift_status_members_unique(self):
        values = [int(m) for m in ShiftStatus]
        assert len(values) == len(set(values))

    def test_user_role_members_unique(self):
        values = [int(m) for m in UserRole]
        assert len(values) == len(set(values))

    def test_request_status_db_values_unique(self):
        db_vals = [m.db_value for m in RequestStatus]
        assert len(db_vals) == len(set(db_vals))
