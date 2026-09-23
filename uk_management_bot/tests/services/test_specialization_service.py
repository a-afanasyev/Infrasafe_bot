"""Unit tests for SpecializationService."""
from unittest.mock import MagicMock, patch

from uk_management_bot.services.specialization_service import SpecializationService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(
    user_id=1,
    telegram_id=100,
    roles='["executor"]',
    specialization=None,
    status="approved",
):
    user = MagicMock()
    user.id = user_id
    user.telegram_id = telegram_id
    user.roles = roles
    user.specialization = specialization
    user.status = status
    return user


def _make_db(user=None, executors=None):
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value.first.return_value = user
    q.filter.return_value.all.return_value = executors or []
    q.filter.return_value.count.return_value = len(executors or [])
    q.filter.return_value.order_by.return_value.count.return_value = 0
    q.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = executors or []
    q.all.return_value = executors or []
    db.query.return_value = q
    db.execute.return_value.scalar.return_value = "2026-01-01"
    return db


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:
    def test_stores_db_reference(self):
        db = MagicMock()
        service = SpecializationService(db)
        assert service.db is db

    def test_available_specializations_not_empty(self):
        service = SpecializationService(MagicMock())
        assert len(service.AVAILABLE_SPECIALIZATIONS) > 0


# ---------------------------------------------------------------------------
# validate_specialization  (pure)
# ---------------------------------------------------------------------------

class TestValidateSpecialization:
    def setup_method(self):
        self.service = SpecializationService(MagicMock())

    def test_valid_specialization_returns_true(self):
        assert self.service.validate_specialization("plumber") is True

    def test_invalid_specialization_returns_false(self):
        assert self.service.validate_specialization("superspecialist") is False

    def test_empty_string_returns_false(self):
        assert self.service.validate_specialization("") is False

    def test_all_available_specs_are_valid(self):
        for spec in self.service.AVAILABLE_SPECIALIZATIONS:
            assert self.service.validate_specialization(spec) is True


# ---------------------------------------------------------------------------
# validate_specializations  (pure)
# ---------------------------------------------------------------------------

class TestValidateSpecializations:
    def setup_method(self):
        self.service = SpecializationService(MagicMock())

    def test_filters_invalid_specs(self):
        result = self.service.validate_specializations(["plumber", "invalid_spec"])
        assert result == ["plumber"]

    def test_removes_duplicates(self):
        result = self.service.validate_specializations(["plumber", "plumber", "electrician"])
        assert result.count("plumber") == 1

    def test_strips_whitespace(self):
        result = self.service.validate_specializations(["  plumber  "])
        assert "plumber" in result

    def test_empty_list_returns_empty(self):
        result = self.service.validate_specializations([])
        assert result == []

    def test_all_invalid_returns_empty(self):
        result = self.service.validate_specializations(["ghost", "phantom"])
        assert result == []

    def test_skips_empty_strings(self):
        result = self.service.validate_specializations(["", "plumber", "  "])
        assert result == ["plumber"]


# ---------------------------------------------------------------------------
# get_user_specializations  (DB-backed)
# ---------------------------------------------------------------------------

class TestGetUserSpecializations:
    def test_returns_empty_when_user_not_found(self):
        db = _make_db(user=None)
        service = SpecializationService(db)
        result = service.get_user_specializations(999)
        assert result == []

    def test_returns_empty_when_no_specialization(self):
        user = _make_user(specialization=None)
        db = _make_db(user=user)
        service = SpecializationService(db)
        result = service.get_user_specializations(1)
        assert result == []

    def test_parses_csv_specialization(self):
        user = _make_user(specialization="plumber,electrician")
        db = _make_db(user=user)
        service = SpecializationService(db)
        result = service.get_user_specializations(1)
        assert "plumber" in result
        assert "electrician" in result

    def test_filters_invalid_specs_from_db(self):
        user = _make_user(specialization="plumber,ghost_spec")
        db = _make_db(user=user)
        service = SpecializationService(db)
        result = service.get_user_specializations(1)
        assert "plumber" in result
        assert "ghost_spec" not in result

    def test_returns_empty_on_exception(self):
        db = MagicMock()
        db.query.side_effect = Exception("DB error")
        service = SpecializationService(db)
        result = service.get_user_specializations(1)
        assert result == []


# ---------------------------------------------------------------------------
# _is_executor  (pure — uses user object)
# ---------------------------------------------------------------------------

class TestIsExecutor:
    def setup_method(self):
        self.service = SpecializationService(MagicMock())

    def test_returns_true_for_executor_role(self):
        user = _make_user(roles='["executor"]')
        assert self.service._is_executor(user) is True

    def test_returns_true_for_multi_role_with_executor(self):
        user = _make_user(roles='["applicant", "executor"]')
        assert self.service._is_executor(user) is True

    def test_returns_false_for_applicant_only(self):
        user = _make_user(roles='["applicant"]')
        assert self.service._is_executor(user) is False

    def test_returns_false_when_roles_is_none(self):
        user = _make_user(roles=None)
        assert self.service._is_executor(user) is False

    def test_returns_false_when_roles_is_invalid_json(self):
        user = _make_user(roles="not-json")
        assert self.service._is_executor(user) is False

    def test_returns_false_for_manager_only(self):
        user = _make_user(roles='["manager"]')
        assert self.service._is_executor(user) is False


# ---------------------------------------------------------------------------
# set_user_specializations  (DB-backed)
# ---------------------------------------------------------------------------

class TestSetUserSpecializations:
    def _db_with_user(self, user):
        db = MagicMock()
        calls = [0]

        def query_side_effect(model):
            q = MagicMock()
            calls[0] += 1
            # All queries return the same user for simplicity
            q.filter.return_value.first.return_value = user
            q.filter.return_value.order_by.return_value.count.return_value = 0
            q.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
            return q

        db.query.side_effect = query_side_effect
        db.execute.return_value.scalar.return_value = "2026-01-01"
        return db

    def test_returns_false_when_user_not_found(self):
        db = _make_db(user=None)
        service = SpecializationService(db)
        result = service.set_user_specializations(999, ["plumber"], updated_by=2)
        assert result is False

    def test_returns_false_when_user_is_not_executor(self):
        user = _make_user(roles='["applicant"]')
        db = self._db_with_user(user)
        service = SpecializationService(db)
        result = service.set_user_specializations(1, ["plumber"], updated_by=2)
        assert result is False

    def test_sets_valid_specializations(self):
        user = _make_user(specialization="plumber")
        db = self._db_with_user(user)
        service = SpecializationService(db)
        result = service.set_user_specializations(1, ["electrician"], updated_by=2)
        assert result is True
        assert "electrician" in user.specialization

    def test_clears_specialization_when_list_empty_or_all_invalid(self):
        user = _make_user(specialization="plumber")
        db = self._db_with_user(user)
        service = SpecializationService(db)
        result = service.set_user_specializations(1, ["invalid_spec"], updated_by=2)
        # Valid specs = [] → specialization set to None
        assert result is True
        assert user.specialization is None

    def test_returns_false_on_db_exception(self):
        db = MagicMock()
        db.query.side_effect = Exception("DB error")
        service = SpecializationService(db)
        result = service.set_user_specializations(1, ["plumber"], updated_by=2)
        assert result is False
        db.rollback.assert_called()


# ---------------------------------------------------------------------------
# format_specializations_list  (mocked get_text)
# ---------------------------------------------------------------------------

class TestFormatSpecializationsList:
    def test_formats_valid_specializations(self):
        service = SpecializationService(MagicMock())
        with patch("uk_management_bot.services.specialization_service.get_text") as mock_get_text:
            mock_get_text.side_effect = lambda key, **kwargs: key.split(".")[-1].title()
            result = service.format_specializations_list(["plumber", "electrician"])
            assert "Plumber" in result
            assert "Electrician" in result

    def test_returns_no_specializations_for_empty_list(self):
        service = SpecializationService(MagicMock())
        with patch("uk_management_bot.services.specialization_service.get_text") as mock_get_text:
            mock_get_text.return_value = "Нет специализаций"
            result = service.format_specializations_list([])
            assert "Нет специализаций" in result

    def test_skips_invalid_specializations(self):
        service = SpecializationService(MagicMock())
        with patch("uk_management_bot.services.specialization_service.get_text") as mock_get_text:
            mock_get_text.return_value = "Нет специализаций"
            result = service.format_specializations_list(["invalid_spec"])
            # Invalid specs are skipped → falls back to no_specializations text
            assert "Нет специализаций" in result
