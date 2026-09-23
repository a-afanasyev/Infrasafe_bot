"""
Unit tests for UserManagementService (mock-based, no DB required).

Covers:
- get_user_stats
- get_employee_stats
- get_residents_by_status / get_users_by_status
- get_staff_users
- get_user_by_id
- format_user_info (detailed, brief)
- _format_user_roles / _format_user_specializations
- format_stats_message
- get_employees_list (various list_type values)
"""
import pytest
from unittest.mock import MagicMock, patch


class _FakeUser:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.telegram_id = kwargs.get("telegram_id", 100)
        self.username = kwargs.get("username", "testuser")
        self.first_name = kwargs.get("first_name", "Иван")
        self.last_name = kwargs.get("last_name", "Иванов")
        self.roles = kwargs.get("roles", '["applicant"]')
        self.active_role = kwargs.get("active_role", "applicant")
        self.role = kwargs.get("role", "applicant")
        self.status = kwargs.get("status", "approved")
        self.phone = kwargs.get("phone", "+998901234567")
        self.specialization = kwargs.get("specialization", None)
        self.created_at = kwargs.get("created_at", None)
        self.updated_at = kwargs.get("updated_at", None)
        self.language = kwargs.get("language", "ru")


def _build_service(db_mock):
    from uk_management_bot.services.user_management_service import UserManagementService
    return UserManagementService(db_mock)


def _mock_query_chain(db_mock, count_val=0, all_val=None):
    """Set up a typical query chain mock that supports filter, count, order_by, offset, limit, all."""
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.offset.return_value = q
    q.limit.return_value = q
    q.count.return_value = count_val
    q.all.return_value = all_val or []
    db_mock.query.return_value = q
    return q


# ===== get_user_stats =====

class TestGetUserStats:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_returns_stats_dict(self):
        q = MagicMock()
        q.filter.return_value = q
        q.count.return_value = 5
        self.db.query.return_value = q
        stats = self.svc.get_user_stats()
        assert "pending" in stats
        assert "approved" in stats
        assert "blocked" in stats
        assert "staff" in stats
        assert "total" in stats

    def test_exception_returns_zeros(self):
        self.db.query.side_effect = Exception("fail")
        stats = self.svc.get_user_stats()
        assert stats["total"] == 0
        assert stats["pending"] == 0


# ===== get_employee_stats =====

class TestGetEmployeeStats:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_returns_employee_stats(self):
        q = MagicMock()
        q.filter.return_value = q
        q.count.return_value = 3
        self.db.query.return_value = q
        stats = self.svc.get_employee_stats()
        assert "pending" in stats
        assert "active" in stats
        assert "blocked" in stats
        assert "executors" in stats
        assert "managers" in stats

    def test_exception_returns_zeros(self):
        self.db.query.side_effect = Exception("fail")
        stats = self.svc.get_employee_stats()
        assert stats["executors"] == 0


# ===== get_residents_by_status =====

class TestGetResidentsByStatus:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_returns_users_and_pagination(self):
        user = _FakeUser()
        _mock_query_chain(self.db, count_val=1, all_val=[user])
        result = self.svc.get_residents_by_status("approved")
        assert result["total"] == 1
        assert result["page"] == 1
        assert len(result["users"]) == 1
        assert result["status"] == "approved"

    def test_pagination_page_2(self):
        _mock_query_chain(self.db, count_val=15, all_val=[])
        result = self.svc.get_residents_by_status("approved", page=2, limit=10)
        assert result["has_prev"] is True
        assert result["has_next"] is False
        assert result["total_pages"] == 2

    def test_exception_returns_empty(self):
        self.db.query.side_effect = Exception("fail")
        result = self.svc.get_residents_by_status("approved")
        assert result["users"] == []
        assert result["total"] == 0


# ===== get_users_by_status =====

class TestGetUsersByStatus:
    def test_delegates_to_get_residents_by_status(self):
        db = MagicMock()
        svc = _build_service(db)
        with patch.object(svc, "get_residents_by_status", return_value={"users": []}) as mock:
            svc.get_users_by_status("pending", page=2, limit=5)
            mock.assert_called_once_with("pending", 2, 5)


# ===== get_staff_users =====

class TestGetStaffUsers:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_returns_staff_with_pagination(self):
        user = _FakeUser(roles='["executor"]')
        _mock_query_chain(self.db, count_val=1, all_val=[user])
        result = self.svc.get_staff_users()
        assert result["type"] == "staff"
        assert result["total"] == 1

    def test_exception_returns_empty(self):
        self.db.query.side_effect = Exception("fail")
        result = self.svc.get_staff_users()
        assert result["users"] == []


# ===== get_user_by_id =====

class TestGetUserById:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_returns_user(self):
        user = _FakeUser()
        self.db.query.return_value.filter.return_value.first.return_value = user
        result = self.svc.get_user_by_id(1)
        assert result == user

    def test_returns_none_when_not_found(self):
        self.db.query.return_value.filter.return_value.first.return_value = None
        result = self.svc.get_user_by_id(999)
        assert result is None

    def test_returns_none_on_exception(self):
        self.db.query.side_effect = Exception("fail")
        result = self.svc.get_user_by_id(1)
        assert result is None


# ===== format_user_info =====

class TestFormatUserInfo:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    @patch("uk_management_bot.services.user_management_service.get_text", side_effect=lambda key, **kw: key)
    def test_detailed_format(self, mock_get_text):
        user = _FakeUser(
            first_name="Иван",
            last_name="Петров",
            username="ipetrov",
            status="approved",
            phone="+998901234567",
            telegram_id=100,
        )
        result = self.svc.format_user_info(user, detailed=True)
        assert "Иван Петров" in result
        assert "@ipetrov" in result
        assert "100" in result
        assert "+998901234567" in result

    @patch("uk_management_bot.services.user_management_service.get_text", side_effect=lambda key, **kw: key)
    def test_brief_format(self, mock_get_text):
        user = _FakeUser(first_name="Иван", last_name="Петров")
        result = self.svc.format_user_info(user, detailed=False)
        assert "Иван Петров" in result
        # brief should not contain phone or telegram_id lines
        assert "+998" not in result

    @patch("uk_management_bot.services.user_management_service.get_text", side_effect=lambda key, **kw: key)
    def test_format_with_no_names(self, mock_get_text):
        user = _FakeUser(first_name=None, last_name=None, username="anon")
        result = self.svc.format_user_info(user, detailed=False)
        assert "anon" in result

    @patch("uk_management_bot.services.user_management_service.get_text", side_effect=lambda key, **kw: key)
    def test_format_with_no_names_no_username(self, mock_get_text):
        user = _FakeUser(first_name=None, last_name=None, username=None, telegram_id=555)
        result = self.svc.format_user_info(user, detailed=False)
        assert "555" in result

    @patch("uk_management_bot.services.user_management_service.get_text", side_effect=lambda key, **kw: key)
    def test_exception_returns_fallback(self, mock_get_text):
        mock_get_text.side_effect = Exception("fail")
        user = _FakeUser()
        result = self.svc.format_user_info(user)
        assert "ошибка" in result.lower()


# ===== _format_user_roles =====

class TestFormatUserRoles:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    @patch("uk_management_bot.services.user_management_service.get_text", side_effect=lambda key, **kw: key)
    def test_formats_roles(self, mock_get_text):
        user = _FakeUser(roles='["applicant", "executor"]', active_role="executor")
        result = self.svc._format_user_roles(user)
        assert "roles.applicant" in result
        assert "*roles.executor*" in result  # active role marked

    @patch("uk_management_bot.services.user_management_service.get_text", side_effect=lambda key, **kw: key)
    def test_empty_roles(self, mock_get_text):
        user = _FakeUser(roles=None)
        result = self.svc._format_user_roles(user)
        assert "roles.none" in result

    @patch("uk_management_bot.services.user_management_service.get_text", side_effect=lambda key, **kw: key)
    def test_non_json_roles_parsed_as_csv(self, mock_get_text):
        # COD-01: canonical parser treats non-JSON as CSV; the token is formatted
        # as a (garbage) role rather than collapsing to roles.none. roles.none
        # is reserved for the empty/NULL case (test_empty_roles above).
        user = _FakeUser(roles="not-json")
        result = self.svc._format_user_roles(user)
        assert "roles.not-json" in result


# ===== _format_user_specializations =====

class TestFormatUserSpecializations:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    @patch("uk_management_bot.services.user_management_service.get_text", side_effect=lambda key, **kw: key)
    def test_formats_specializations(self, mock_get_text):
        # Значения нормализуются к канону: `electricity`/`plumbing` — legacy
        # (и вовсе ключи категорий), в форме их нет, но в старых строках БД
        # они встречаются и обязаны резолвиться, а не отбрасываться.
        user = _FakeUser(
            roles='["executor"]',
            specialization="electricity,plumbing"
        )
        result = self.svc._format_user_specializations(user)
        assert "specializations.electrician" in result
        assert "specializations.plumber" in result

    @patch("uk_management_bot.services.user_management_service.get_text", side_effect=lambda key, **kw: key)
    def test_empty_specialization(self, mock_get_text):
        user = _FakeUser(roles='["executor"]', specialization=None)
        result = self.svc._format_user_specializations(user)
        assert result == ""

    @patch("uk_management_bot.services.user_management_service.get_text", side_effect=lambda key, **kw: key)
    def test_non_executor_returns_empty(self, mock_get_text):
        user = _FakeUser(roles='["applicant"]', specialization="electricity")
        result = self.svc._format_user_specializations(user)
        assert result == ""


# ===== format_stats_message =====

class TestFormatStatsMessage:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    @patch("uk_management_bot.services.user_management_service.get_text",
           return_value="Всего: {total}, Ожидающих: {pending}")
    def test_formats_stats(self, mock_get_text):
        stats = {"total": 100, "pending": 5, "approved": 90, "blocked": 5, "staff": 10}
        result = self.svc.format_stats_message(stats)
        assert "100" in result
        assert "5" in result

    @patch("uk_management_bot.services.user_management_service.get_text",
           side_effect=Exception("format error"))
    def test_exception_returns_fallback(self, mock_get_text):
        stats = {"total": 42}
        result = self.svc.format_stats_message(stats)
        assert "42" in result


# ===== get_employees_list =====

class TestGetEmployeesList:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    @pytest.mark.parametrize("list_type", ["pending", "active", "blocked", "executors", "managers", "all"])
    def test_returns_employees_dict(self, list_type):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.offset.return_value = q
        q.limit.return_value = q
        q.count.return_value = 2
        q.all.return_value = [_FakeUser(), _FakeUser(id=2)]
        self.db.query.return_value = q

        result = self.svc.get_employees_list(list_type)
        assert "employees" in result
        assert "current_page" in result
        assert "total_pages" in result
        assert "total_employees" in result
        assert result["total_employees"] == 2

    def test_exception_returns_empty(self):
        self.db.query.side_effect = Exception("fail")
        result = self.svc.get_employees_list("active")
        assert result["employees"] == []
        assert result["total_employees"] == 0
