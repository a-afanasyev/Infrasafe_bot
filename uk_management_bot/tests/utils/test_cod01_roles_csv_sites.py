"""COD-01 regression: converted call sites must read CSV roles correctly.

`users.roles` is a `Column(Text)` — a legacy CSV value (e.g. "executor,manager")
is representable. Before COD-01 the ~28 inline `json.loads(user.roles)` sites
raised `JSONDecodeError` on CSV and fell back to `[]`, silently denying an
executor their rights (audit #4). These sites now delegate to the canonical
`parse_roles_safe`, which understands JSON *and* CSV. Prod currently holds no
CSV values, so this locks the fix against regression rather than a live bug.
"""
from unittest.mock import MagicMock

from uk_management_bot.services.specialization_service import SpecializationService
from uk_management_bot.utils.auth_helpers import parse_roles_safe


def _user(roles):
    u = MagicMock()
    u.telegram_id = 1
    u.id = 1
    u.roles = roles
    u.active_role = None
    u.specialization = None
    return u


class TestSpecializationServiceCsv:
    def _svc(self):
        return SpecializationService(MagicMock())

    def test_is_executor_csv(self):
        assert self._svc()._is_executor(_user("applicant,executor")) is True

    def test_is_executor_json_still_works(self):
        assert self._svc()._is_executor(_user('["executor"]')) is True

    def test_is_executor_absent(self):
        assert self._svc()._is_executor(_user("applicant,manager")) is False

    def test_is_executor_none_roles(self):
        assert self._svc()._is_executor(_user(None)) is False


class TestParseRolesSafeCsv:
    """Канонический парсер, к которому делегируют все COD-01 call sites."""

    def test_csv(self):
        assert parse_roles_safe("executor,manager") == ["executor", "manager"]

    def test_csv_strips_whitespace(self):
        assert parse_roles_safe("applicant, executor") == ["applicant", "executor"]

    def test_json_still_works(self):
        assert parse_roles_safe('["executor", "applicant"]') == ["executor", "applicant"]

    def test_none(self):
        assert parse_roles_safe(None) == []
