"""Unit tests for ProfileService."""
from unittest.mock import MagicMock, patch

from uk_management_bot.services.profile_service import ProfileService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_apartment(apt_id=1, apartment_number="101", is_primary=True, is_owner=True):
    apt = MagicMock()
    apt.id = apt_id
    apt.apartment_number = apartment_number
    apt.full_address = f"ул. Тестовая, д. 1, кв. {apartment_number}"
    return apt


def _make_user_apartment(apartment, status="approved", is_primary=True, is_owner=True):
    ua = MagicMock()
    ua.status = status
    ua.is_primary = is_primary
    ua.is_owner = is_owner
    ua.apartment = apartment
    return ua


def _make_user(
    user_id=1,
    telegram_id=100,
    status="approved",
    role="applicant",
    roles='["applicant"]',
    active_role="applicant",
    language="ru",
    specialization=None,
    first_name="Test",
    last_name="User",
    username="testuser",
    phone=None,
    user_apartments=None,
):
    user = MagicMock()
    user.id = user_id
    user.telegram_id = telegram_id
    user.status = status
    user.role = role
    user.roles = roles
    user.active_role = active_role
    user.language = language
    user.specialization = specialization
    user.first_name = first_name
    user.last_name = last_name
    user.username = username
    user.phone = phone
    user.created_at = None
    user.updated_at = None
    user.user_apartments = user_apartments or []
    return user


def _make_db(user=None):
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value.first.return_value = user
    db.query.return_value = q
    return db


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:
    def test_stores_db_reference(self):
        db = MagicMock()
        service = ProfileService(db)
        assert service.db is db


# ---------------------------------------------------------------------------
# get_user_profile_data
# ---------------------------------------------------------------------------

class TestGetUserProfileData:
    def test_returns_none_when_user_not_found(self):
        db = _make_db(user=None)
        service = ProfileService(db)
        result = service.get_user_profile_data(999)
        assert result is None

    def test_returns_none_on_exception(self):
        db = MagicMock()
        db.query.side_effect = Exception("DB error")
        service = ProfileService(db)
        result = service.get_user_profile_data(100)
        assert result is None

    def test_returns_profile_dict_for_valid_user(self):
        user = _make_user()
        db = _make_db(user=user)
        service = ProfileService(db)
        result = service.get_user_profile_data(100)
        assert result is not None
        assert result["telegram_id"] == 100
        assert result["user_id"] == 1

    def test_parses_roles_from_json(self):
        user = _make_user(roles='["applicant", "executor"]')
        db = _make_db(user=user)
        service = ProfileService(db)
        result = service.get_user_profile_data(100)
        assert "executor" in result["roles"]

    def test_defaults_roles_to_applicant_on_parse_error(self):
        user = _make_user(roles="not-valid-json")
        db = _make_db(user=user)
        service = ProfileService(db)
        result = service.get_user_profile_data(100)
        assert result["roles"] == ["applicant"]

    def test_active_role_corrected_if_not_in_roles(self):
        user = _make_user(
            roles='["applicant"]',
            active_role="executor",  # not in roles
        )
        db = _make_db(user=user)
        service = ProfileService(db)
        result = service.get_user_profile_data(100)
        assert result["active_role"] == "applicant"

    def test_parses_csv_specialization(self):
        user = _make_user(specialization="electrician,plumber")
        db = _make_db(user=user)
        service = ProfileService(db)
        result = service.get_user_profile_data(100)
        assert "electrician" in result["specializations"]
        assert "plumber" in result["specializations"]

    def test_parses_json_array_specialization(self):
        user = _make_user(specialization='["electrician", "plumber"]')
        db = _make_db(user=user)
        service = ProfileService(db)
        result = service.get_user_profile_data(100)
        assert "electrician" in result["specializations"]

    def test_no_specialization_returns_empty_list(self):
        user = _make_user(specialization=None)
        db = _make_db(user=user)
        service = ProfileService(db)
        result = service.get_user_profile_data(100)
        assert result["specializations"] == []

    def test_includes_approved_apartments(self):
        apt = _make_apartment()
        ua = _make_user_apartment(apt, status="approved", is_primary=True, is_owner=True)
        user = _make_user(user_apartments=[ua])
        db = _make_db(user=user)
        service = ProfileService(db)
        result = service.get_user_profile_data(100)
        assert len(result["apartments"]) == 1
        assert result["apartments"][0]["is_primary"] is True

    def test_excludes_unapproved_apartments(self):
        apt = _make_apartment()
        ua = _make_user_apartment(apt, status="pending")
        user = _make_user(user_apartments=[ua])
        db = _make_db(user=user)
        service = ProfileService(db)
        result = service.get_user_profile_data(100)
        assert result["apartments"] == []

    def test_status_defaults_to_pending_if_none(self):
        user = _make_user(status=None)
        user.status = None
        db = _make_db(user=user)
        service = ProfileService(db)
        result = service.get_user_profile_data(100)
        assert result["status"] == "pending"

    def test_language_defaults_to_ru_if_none(self):
        user = _make_user(language=None)
        user.language = None
        db = _make_db(user=user)
        service = ProfileService(db)
        result = service.get_user_profile_data(100)
        assert result["language"] == "ru"


# ---------------------------------------------------------------------------
# validate_profile_data  (pure method — no DB)
# ---------------------------------------------------------------------------

class TestValidateProfileData:
    def setup_method(self):
        self.service = ProfileService(MagicMock())

    def _valid_data(self):
        return {
            "telegram_id": 100,
            "roles": ["applicant"],
            "active_role": "applicant",
            "status": "approved",
            "phone": None,
        }

    def test_returns_empty_list_for_valid_data(self):
        issues = self.service.validate_profile_data(self._valid_data())
        assert issues == []

    def test_returns_issue_when_no_data(self):
        issues = self.service.validate_profile_data(None)
        assert len(issues) > 0

    def test_returns_issue_when_no_telegram_id(self):
        data = self._valid_data()
        data["telegram_id"] = None
        issues = self.service.validate_profile_data(data)
        assert any("telegram_id" in i for i in issues)

    def test_returns_issue_when_roles_not_list(self):
        data = self._valid_data()
        data["roles"] = "applicant"
        issues = self.service.validate_profile_data(data)
        assert any("рол" in i.lower() for i in issues)

    def test_returns_issue_when_active_role_not_in_roles(self):
        data = self._valid_data()
        data["roles"] = ["applicant"]
        data["active_role"] = "executor"
        issues = self.service.validate_profile_data(data)
        assert any("активна" in i.lower() or "active" in i.lower() for i in issues)

    def test_returns_issue_for_invalid_status(self):
        data = self._valid_data()
        data["status"] = "unknown"
        issues = self.service.validate_profile_data(data)
        assert any("статус" in i.lower() for i in issues)

    def test_valid_statuses_accepted(self):
        for status in ["pending", "approved", "blocked"]:
            data = self._valid_data()
            data["status"] = status
            issues = self.service.validate_profile_data(data)
            assert not any("статус" in i.lower() for i in issues)

    def test_returns_issue_for_invalid_phone(self):
        data = self._valid_data()
        data["phone"] = "123"  # too short
        issues = self.service.validate_profile_data(data)
        assert any("телефон" in i.lower() for i in issues)

    def test_valid_phone_accepted(self):
        data = self._valid_data()
        data["phone"] = "+998901234567"
        issues = self.service.validate_profile_data(data)
        assert not any("телефон" in i.lower() for i in issues)


# ---------------------------------------------------------------------------
# format_profile_text  (pure — mocked get_text)
# ---------------------------------------------------------------------------

class TestFormatProfileText:
    def setup_method(self):
        self.service = ProfileService(MagicMock())

    def _profile_data(self, **kwargs):
        base = {
            "telegram_id": 100,
            "user_id": 1,
            "username": "testuser",
            "first_name": "Test",
            "last_name": "User",
            "roles": ["applicant"],
            "active_role": "applicant",
            "status": "approved",
            "language": "ru",
            "phone": None,
            "apartments": [],
            "specializations": [],
        }
        base.update(kwargs)
        return base

    def test_returns_error_text_for_none_data(self):
        with patch("uk_management_bot.services.profile_service.get_text") as mock_get_text:
            mock_get_text.return_value = "Error"
            result = self.service.format_profile_text(None, language="ru")
            assert result == "Error"

    def test_includes_username_when_present(self):
        with patch("uk_management_bot.services.profile_service.get_text") as mock_get_text:
            mock_get_text.return_value = ""
            result = self.service.format_profile_text(self._profile_data(), "ru")
            assert "@testuser" in result

    def test_includes_full_name(self):
        with patch("uk_management_bot.services.profile_service.get_text") as mock_get_text:
            mock_get_text.return_value = ""
            result = self.service.format_profile_text(self._profile_data(), "ru")
            assert "Test" in result
            assert "User" in result

    def test_includes_phone_when_present(self):
        with patch("uk_management_bot.services.profile_service.get_text") as mock_get_text:
            mock_get_text.return_value = ""
            data = self._profile_data(phone="+998901234567")
            result = self.service.format_profile_text(data, "ru")
            assert "+998901234567" in result

    def test_shows_all_roles_when_multiple(self):
        with patch("uk_management_bot.services.profile_service.get_text") as mock_get_text:
            mock_get_text.return_value = "some_role"
            data = self._profile_data(roles=["applicant", "executor"])
            self.service.format_profile_text(data, "ru")
            # get_text called for both roles
            assert mock_get_text.call_count > 0

    def test_shows_apartment_address(self):
        with patch("uk_management_bot.services.profile_service.get_text") as mock_get_text:
            mock_get_text.return_value = ""
            data = self._profile_data(apartments=[
                {"address": "ул. Тестовая, 1", "is_primary": True, "is_owner": True}
            ])
            result = self.service.format_profile_text(data, "ru")
            assert "ул. Тестовая, 1" in result

    def test_primary_apartment_marked_with_star(self):
        with patch("uk_management_bot.services.profile_service.get_text") as mock_get_text:
            mock_get_text.return_value = ""
            data = self._profile_data(apartments=[
                {"address": "Test St", "is_primary": True, "is_owner": False}
            ])
            result = self.service.format_profile_text(data, "ru")
            assert "⭐" in result
