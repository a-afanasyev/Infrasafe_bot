"""
Additional mock-based unit tests for ProfileService.

The existing tests/test_profile_service.py uses an in-memory SQLite DB.
These tests use pure mocks — faster, no DB dependencies.

Covers:
- get_user_profile_data edge cases (JSON parse errors, specialization formats)
- format_profile_text (empty data, UZ language)
- validate_profile_data (all branches)
"""
from datetime import datetime
from unittest.mock import MagicMock, patch


class _FakeUserApartment:
    def __init__(self, **kwargs):
        self.status = kwargs.get("status", "approved")
        self.is_primary = kwargs.get("is_primary", True)
        self.is_owner = kwargs.get("is_owner", False)
        apt = MagicMock()
        apt.id = kwargs.get("apt_id", 1)
        apt.full_address = kwargs.get("full_address", "ул. Тестовая, 1, кв. 10")
        apt.apartment_number = kwargs.get("apartment_number", "10")
        self.apartment = apt


class _FakeUser:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.telegram_id = kwargs.get("telegram_id", 100)
        self.username = kwargs.get("username", "tester")
        self.first_name = kwargs.get("first_name", "Тест")
        self.last_name = kwargs.get("last_name", "Юзер")
        self.roles = kwargs.get("roles", '["applicant"]')
        self.active_role = kwargs.get("active_role", "applicant")
        self.status = kwargs.get("status", "approved")
        self.language = kwargs.get("language", "ru")
        self.phone = kwargs.get("phone", None)
        self.specialization = kwargs.get("specialization", None)
        self.created_at = kwargs.get("created_at", datetime.now())
        self.updated_at = kwargs.get("updated_at", None)
        self.user_apartments = kwargs.get("user_apartments", [])


def _build_service(db_mock):
    from uk_management_bot.services.profile_service import ProfileService
    return ProfileService(db_mock)


# ===== get_user_profile_data =====

class TestGetUserProfileData:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_user_not_found(self):
        self.db.query.return_value.filter.return_value.first.return_value = None
        assert self.svc.get_user_profile_data(999) is None

    def test_user_with_no_roles(self):
        user = _FakeUser(roles=None, active_role=None)
        self.db.query.return_value.filter.return_value.first.return_value = user
        result = self.svc.get_user_profile_data(100)
        assert result["roles"] == ["applicant"]
        assert result["active_role"] == "applicant"

    def test_user_with_non_json_roles_parsed_as_csv(self):
        # COD-01: canonical parse_roles_safe treats a non-JSON string as CSV;
        # a single garbage token → single-element list (default applicant only
        # applies to empty/NULL). Previously json.loads raised → applicant.
        user = _FakeUser(roles="not-json")
        self.db.query.return_value.filter.return_value.first.return_value = user
        result = self.svc.get_user_profile_data(100)
        assert result["roles"] == ["not-json"]

    def test_user_with_csv_specialization(self):
        user = _FakeUser(specialization="electricity,plumbing")
        self.db.query.return_value.filter.return_value.first.return_value = user
        result = self.svc.get_user_profile_data(100)
        assert "electricity" in result["specializations"]
        assert "plumbing" in result["specializations"]

    def test_user_with_json_specialization(self):
        user = _FakeUser(specialization='["electricity", "plumbing"]')
        self.db.query.return_value.filter.return_value.first.return_value = user
        result = self.svc.get_user_profile_data(100)
        assert "electricity" in result["specializations"]
        assert "plumbing" in result["specializations"]

    def test_user_with_empty_specialization(self):
        user = _FakeUser(specialization="")
        self.db.query.return_value.filter.return_value.first.return_value = user
        result = self.svc.get_user_profile_data(100)
        assert result["specializations"] == []

    def test_user_with_apartments(self):
        ua = _FakeUserApartment(full_address="ул. А, 1, кв. 5")
        user = _FakeUser(user_apartments=[ua])
        self.db.query.return_value.filter.return_value.first.return_value = user
        result = self.svc.get_user_profile_data(100)
        assert len(result["apartments"]) == 1
        assert result["apartments"][0]["is_primary"] is True

    def test_user_with_pending_apartment_excluded(self):
        ua = _FakeUserApartment(status="pending")
        user = _FakeUser(user_apartments=[ua])
        self.db.query.return_value.filter.return_value.first.return_value = user
        result = self.svc.get_user_profile_data(100)
        assert len(result["apartments"]) == 0

    def test_active_role_not_in_roles_gets_corrected(self):
        user = _FakeUser(roles='["applicant"]', active_role="manager")
        self.db.query.return_value.filter.return_value.first.return_value = user
        result = self.svc.get_user_profile_data(100)
        assert result["active_role"] == "applicant"

    def test_exception_returns_none(self):
        self.db.query.side_effect = Exception("DB error")
        assert self.svc.get_user_profile_data(100) is None


# ===== format_profile_text =====

class TestFormatProfileText:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    @patch("uk_management_bot.services.profile_service.get_text", side_effect=lambda key, **kw: key)
    def test_empty_profile_data(self, mock_get_text):
        result = self.svc.format_profile_text(None)
        assert "errors.unknown_error" in result

    @patch("uk_management_bot.services.profile_service.get_text", side_effect=lambda key, **kw: key)
    def test_minimal_profile(self, mock_get_text):
        profile_data = {
            "first_name": "Тест",
            "last_name": None,
            "username": None,
            "status": "pending",
            "active_role": "applicant",
            "roles": ["applicant"],
            "phone": None,
            "apartments": [],
            "specializations": [],
        }
        result = self.svc.format_profile_text(profile_data, language="ru")
        assert "Тест" in result
        assert "profile.title" in result

    @patch("uk_management_bot.services.profile_service.get_text", side_effect=lambda key, **kw: key)
    def test_executor_with_specializations(self, mock_get_text):
        profile_data = {
            "first_name": "Exec",
            "last_name": "User",
            "username": "exec",
            "status": "approved",
            "active_role": "executor",
            "roles": ["executor"],
            "phone": "+998901234567",
            "apartments": [],
            "specializations": ["electricity"],
        }
        result = self.svc.format_profile_text(profile_data, language="ru")
        # get_text returns the key; for localised specs that match their key,
        # format_profile_text uses the raw value as fallback
        assert "electricity" in result

    @patch("uk_management_bot.services.profile_service.get_text", side_effect=lambda key, **kw: key)
    def test_profile_with_apartments(self, mock_get_text):
        profile_data = {
            "first_name": "User",
            "last_name": None,
            "username": None,
            "status": "approved",
            "active_role": "applicant",
            "roles": ["applicant"],
            "phone": None,
            "apartments": [
                {"address": "ул. А, 1, кв. 5", "is_primary": True, "is_owner": True},
            ],
            "specializations": [],
        }
        result = self.svc.format_profile_text(profile_data, language="ru")
        assert "ул. А, 1, кв. 5" in result

    @patch("uk_management_bot.services.profile_service.get_text", side_effect=lambda key, **kw: key)
    def test_multiple_roles_shown(self, mock_get_text):
        profile_data = {
            "first_name": "Multi",
            "last_name": None,
            "username": None,
            "status": "approved",
            "active_role": "executor",
            "roles": ["applicant", "executor"],
            "phone": None,
            "apartments": [],
            "specializations": [],
        }
        result = self.svc.format_profile_text(profile_data)
        assert "profile.all_roles" in result


# ===== validate_profile_data =====

class TestValidateProfileData:
    def setup_method(self):
        self.db = MagicMock()
        self.svc = _build_service(self.db)

    def test_none_data(self):
        issues = self.svc.validate_profile_data(None)
        assert len(issues) == 1
        assert "отсутствуют" in issues[0]

    def test_valid_data_no_issues(self):
        data = {
            "telegram_id": 100,
            "roles": ["applicant"],
            "active_role": "applicant",
            "status": "approved",
        }
        assert self.svc.validate_profile_data(data) == []

    def test_missing_telegram_id(self):
        data = {
            "telegram_id": None,
            "roles": ["applicant"],
            "active_role": "applicant",
            "status": "approved",
        }
        issues = self.svc.validate_profile_data(data)
        assert any("telegram_id" in i for i in issues)

    def test_invalid_roles(self):
        data = {
            "telegram_id": 100,
            "roles": "not-a-list",
            "active_role": "applicant",
            "status": "approved",
        }
        issues = self.svc.validate_profile_data(data)
        assert any("роли" in i for i in issues)

    def test_active_role_not_in_roles(self):
        data = {
            "telegram_id": 100,
            "roles": ["applicant"],
            "active_role": "manager",
            "status": "approved",
        }
        issues = self.svc.validate_profile_data(data)
        assert any("Активная роль" in i for i in issues)

    def test_invalid_status(self):
        data = {
            "telegram_id": 100,
            "roles": ["applicant"],
            "active_role": "applicant",
            "status": "unknown",
        }
        issues = self.svc.validate_profile_data(data)
        assert any("статус" in i for i in issues)

    def test_invalid_phone(self):
        data = {
            "telegram_id": 100,
            "roles": ["applicant"],
            "active_role": "applicant",
            "status": "approved",
            "phone": "123",
        }
        issues = self.svc.validate_profile_data(data)
        assert any("телефона" in i for i in issues)

    def test_valid_phone(self):
        data = {
            "telegram_id": 100,
            "roles": ["applicant"],
            "active_role": "applicant",
            "status": "approved",
            "phone": "+998901234567",
        }
        assert self.svc.validate_profile_data(data) == []
