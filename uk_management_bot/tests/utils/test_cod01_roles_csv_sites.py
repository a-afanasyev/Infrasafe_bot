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
from uk_management_bot.services.user_management_service import UserManagementService


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


class TestUserManagementServiceCsv:
    def _svc(self):
        return UserManagementService(MagicMock())

    def test_is_user_staff_csv(self):
        assert self._svc().is_user_staff(_user("applicant,manager")) is True

    def test_is_user_employee_csv(self):
        # Previously used substring '"executor"' which never matched CSV.
        assert self._svc().is_user_employee(_user("executor,applicant")) is True

    def test_is_user_employee_applicant_only(self):
        assert self._svc().is_user_employee(_user("applicant")) is False

    def test_get_user_role_list_csv(self):
        assert self._svc().get_user_role_list(_user("executor,manager")) == [
            "executor",
            "manager",
        ]

    def test_get_user_role_list_none(self):
        assert self._svc().get_user_role_list(_user(None)) == []
