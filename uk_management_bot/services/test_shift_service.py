"""Unit tests for ShiftService."""
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime

from uk_management_bot.services.shift_service import ShiftService
from uk_management_bot.utils.constants import (
    SHIFT_STATUS_ACTIVE,
    SHIFT_STATUS_COMPLETED,
    ROLE_EXECUTOR,
    ROLE_MANAGER,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(telegram_id=100, user_id=1, roles='["executor"]'):
    user = MagicMock()
    user.id = user_id
    user.telegram_id = telegram_id
    user.roles = roles
    return user


def _make_shift(shift_id=10, user_id=1, status=SHIFT_STATUS_ACTIVE):
    shift = MagicMock()
    shift.id = shift_id
    shift.user_id = user_id
    shift.status = status
    shift.start_time = datetime(2026, 4, 2, 9, 0, 0)
    shift.end_time = None
    shift.notes = None
    return shift


def _make_db(user=None, shift=None):
    """Build a minimal Session mock with a chained query pattern."""
    db = MagicMock()

    def _query_side_effect(model):
        q = MagicMock()

        def _filter(*args, **kwargs):
            fq = MagicMock()
            fq.first.return_value = user if "User" in str(model) else shift
            return fq

        q.filter.side_effect = _filter
        return q

    db.query.side_effect = _query_side_effect
    return db


# ---------------------------------------------------------------------------
# is_user_in_active_shift
# ---------------------------------------------------------------------------

class TestIsUserInActiveShift:
    def test_returns_true_when_active_shift_exists(self):
        user = _make_user()
        shift = _make_shift(status=SHIFT_STATUS_ACTIVE)

        db = MagicMock()
        # First query: User lookup
        user_q = MagicMock()
        user_q.filter.return_value.first.return_value = user
        # Second query: Shift lookup
        shift_q = MagicMock()
        shift_q.filter.return_value.first.return_value = shift

        db.query.side_effect = [user_q, shift_q]

        service = ShiftService(db)
        assert service.is_user_in_active_shift(100) is True

    def test_returns_false_when_no_active_shift(self):
        user = _make_user()

        db = MagicMock()
        user_q = MagicMock()
        user_q.filter.return_value.first.return_value = user
        shift_q = MagicMock()
        shift_q.filter.return_value.first.return_value = None

        db.query.side_effect = [user_q, shift_q]

        service = ShiftService(db)
        assert service.is_user_in_active_shift(100) is False

    def test_returns_false_when_user_not_found(self):
        db = MagicMock()
        user_q = MagicMock()
        user_q.filter.return_value.first.return_value = None
        db.query.return_value = user_q

        service = ShiftService(db)
        assert service.is_user_in_active_shift(999) is False

    def test_returns_false_on_db_exception(self):
        db = MagicMock()
        db.query.side_effect = Exception("DB error")

        service = ShiftService(db)
        assert service.is_user_in_active_shift(100) is False


# ---------------------------------------------------------------------------
# get_active_shift
# ---------------------------------------------------------------------------

class TestGetActiveShift:
    def test_returns_shift_when_exists(self):
        user = _make_user()
        shift = _make_shift(status=SHIFT_STATUS_ACTIVE)

        db = MagicMock()
        user_q = MagicMock()
        user_q.filter.return_value.first.return_value = user
        shift_q = MagicMock()
        shift_q.filter.return_value.first.return_value = shift

        db.query.side_effect = [user_q, shift_q]

        service = ShiftService(db)
        result = service.get_active_shift(100)
        assert result is shift

    def test_returns_none_when_user_not_found(self):
        db = MagicMock()
        user_q = MagicMock()
        user_q.filter.return_value.first.return_value = None
        db.query.return_value = user_q

        service = ShiftService(db)
        assert service.get_active_shift(999) is None

    def test_returns_none_when_no_active_shift(self):
        user = _make_user()

        db = MagicMock()
        user_q = MagicMock()
        user_q.filter.return_value.first.return_value = user
        shift_q = MagicMock()
        shift_q.filter.return_value.first.return_value = None

        db.query.side_effect = [user_q, shift_q]

        service = ShiftService(db)
        assert service.get_active_shift(100) is None

    def test_returns_none_on_exception(self):
        db = MagicMock()
        db.query.side_effect = Exception("Connection lost")

        service = ShiftService(db)
        assert service.get_active_shift(100) is None


# ---------------------------------------------------------------------------
# start_shift
# ---------------------------------------------------------------------------

class TestStartShift:
    def _db_with_user_no_shift(self, user):
        """DB where user is found, shift query returns None (no existing shift)."""
        db = MagicMock()
        calls = []

        def _query(model):
            calls.append(model)
            q = MagicMock()
            # User is always found; Shift queries return None
            from uk_management_bot.database.models.user import User as UserModel
            if model is UserModel:
                q.filter.return_value.first.return_value = user
            else:
                q.filter.return_value.first.return_value = None
            return q

        db.query.side_effect = _query
        return db

    def test_success_executor_role(self):
        user = _make_user(roles='["executor"]')
        db = self._db_with_user_no_shift(user)

        with patch(
            "uk_management_bot.services.shift_service.notify_shift_started"
        ):
            service = ShiftService(db)
            result = service.start_shift(100)

        assert result["success"] is True
        assert result["message"] == "Смена начата"
        assert result["shift"] is not None
        db.add.assert_called()
        db.commit.assert_called()

    def test_success_manager_role(self):
        user = _make_user(roles='["manager"]')
        db = self._db_with_user_no_shift(user)

        with patch(
            "uk_management_bot.services.shift_service.notify_shift_started"
        ):
            service = ShiftService(db)
            result = service.start_shift(100)

        assert result["success"] is True

    def test_user_not_found(self):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        db.query.return_value = q

        service = ShiftService(db)
        result = service.start_shift(999)

        assert result["success"] is False
        assert "не найден" in result["message"]
        assert result["shift"] is None

    def test_wrong_role_applicant_only(self):
        user = _make_user(roles='["applicant"]')
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.first.return_value = user
        db.query.return_value = q

        service = ShiftService(db)
        result = service.start_shift(100)

        assert result["success"] is False
        assert "запрещен" in result["message"].lower() or "Доступ" in result["message"]
        assert result["shift"] is None

    def test_wrong_role_empty_roles(self):
        user = _make_user(roles=None)
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.first.return_value = user
        db.query.return_value = q

        service = ShiftService(db)
        result = service.start_shift(100)

        assert result["success"] is False

    def test_notes_passed_to_shift(self):
        user = _make_user(roles='["executor"]')
        db = self._db_with_user_no_shift(user)

        created_shifts = []

        original_add = db.add

        def capture_add(obj):
            from uk_management_bot.database.models.shift import Shift as ShiftModel
            if isinstance(obj, ShiftModel):
                created_shifts.append(obj)

        db.add.side_effect = capture_add

        with patch(
            "uk_management_bot.services.shift_service.notify_shift_started"
        ):
            service = ShiftService(db)
            service.start_shift(100, notes="Test note")

        # Shift was added (captured or via mock)
        db.add.assert_called()

    def test_db_commit_failure_returns_error(self):
        user = _make_user(roles='["executor"]')
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.first.return_value = user
        db.query.return_value = q
        db.commit.side_effect = Exception("DB commit failed")

        service = ShiftService(db)
        result = service.start_shift(100)

        assert result["success"] is False
        db.rollback.assert_called()


# ---------------------------------------------------------------------------
# end_shift
# ---------------------------------------------------------------------------

class TestEndShift:
    def _db_with_user_and_shift(self, user, shift):
        db = MagicMock()

        from uk_management_bot.database.models.user import User as UserModel
        from uk_management_bot.database.models.shift import Shift as ShiftModel

        def _query(model):
            q = MagicMock()
            if model is UserModel:
                q.filter.return_value.first.return_value = user
            elif model is ShiftModel:
                q.filter.return_value.first.return_value = shift
            else:
                q.filter.return_value.first.return_value = None
            return q

        db.query.side_effect = _query
        return db

    def test_success(self):
        user = _make_user()
        shift = _make_shift(status=SHIFT_STATUS_ACTIVE)
        db = self._db_with_user_and_shift(user, shift)

        with patch(
            "uk_management_bot.services.shift_service.notify_shift_ended"
        ):
            service = ShiftService(db)
            result = service.end_shift(100)

        assert result["success"] is True
        assert result["message"] == "Смена завершена"
        assert shift.status == SHIFT_STATUS_COMPLETED
        assert shift.end_time is not None

    def test_user_not_found(self):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value.first.return_value = None
        db.query.return_value = q

        service = ShiftService(db)
        result = service.end_shift(999)

        assert result["success"] is False
        assert "не найден" in result["message"]

    def test_no_active_shift(self):
        user = _make_user()

        db = MagicMock()
        from uk_management_bot.database.models.user import User as UserModel
        from uk_management_bot.database.models.shift import Shift as ShiftModel

        def _query(model):
            q = MagicMock()
            if model is UserModel:
                q.filter.return_value.first.return_value = user
            else:
                q.filter.return_value.first.return_value = None
            return q

        db.query.side_effect = _query

        service = ShiftService(db)
        result = service.end_shift(100)

        assert result["success"] is False
        assert "активной смены" in result["message"].lower() or "Нет" in result["message"]

    def test_notes_appended_to_existing_notes(self):
        user = _make_user()
        shift = _make_shift(status=SHIFT_STATUS_ACTIVE)
        shift.notes = "existing note"

        db = self._db_with_user_and_shift(user, shift)

        with patch(
            "uk_management_bot.services.shift_service.notify_shift_ended"
        ):
            service = ShiftService(db)
            service.end_shift(100, notes="extra note")

        assert "extra note" in shift.notes

    def test_notes_set_when_no_prior_notes(self):
        user = _make_user()
        shift = _make_shift(status=SHIFT_STATUS_ACTIVE)
        shift.notes = None

        db = self._db_with_user_and_shift(user, shift)

        with patch(
            "uk_management_bot.services.shift_service.notify_shift_ended"
        ):
            service = ShiftService(db)
            service.end_shift(100, notes="my note")

        assert shift.notes == "my note"

    def test_db_exception_returns_error(self):
        user = _make_user()
        shift = _make_shift(status=SHIFT_STATUS_ACTIVE)

        db = self._db_with_user_and_shift(user, shift)
        db.commit.side_effect = Exception("DB error")

        service = ShiftService(db)
        result = service.end_shift(100)

        assert result["success"] is False
        db.rollback.assert_called()
