"""Tests for profile schemas and constants (uk_management_bot/api/profile/router.py)."""
import pytest
from pydantic import ValidationError

from uk_management_bot.api.profile.router import (
    MAX_UPLOAD_SIZE,
    ALLOWED_LANGUAGES,
    ProfileOut,
    UpdateProfileBody,
    RoleSwitchBody,
    RoleSwitchOut,
)


# ═══════════════════════ Constants ═══════════════════════


class TestProfileConstants:

    def test_max_upload_size_is_10mb(self):
        assert MAX_UPLOAD_SIZE == 10 * 1024 * 1024

    def test_allowed_languages(self):
        assert "ru" in ALLOWED_LANGUAGES
        assert "uz" in ALLOWED_LANGUAGES
        assert len(ALLOWED_LANGUAGES) == 2


# ═══════════════════════ ProfileOut ═══════════════════════


class TestProfileOut:

    def test_valid_minimal(self):
        profile = ProfileOut(id=1, telegram_id=123456)
        assert profile.id == 1
        assert profile.telegram_id == 123456
        assert profile.language == "ru"
        assert profile.status == "pending"
        assert profile.verification_status == "pending"
        assert profile.roles is None
        assert profile.active_role is None

    def test_valid_full(self):
        profile = ProfileOut(
            id=1, telegram_id=123456,
            first_name="Ivan", last_name="Petrov",
            phone="+998901234567", email="ivan@test.com",
            language="uz", status="approved",
            verification_status="approved",
            roles=["executor", "manager"],
            active_role="executor",
        )
        assert profile.first_name == "Ivan"
        assert profile.language == "uz"
        assert profile.roles == ["executor", "manager"]
        assert profile.active_role == "executor"

    def test_from_attributes_config(self):
        assert ProfileOut.model_config["from_attributes"] is True

    def test_from_user_classmethod(self):
        """Test from_user with a mock user object."""
        from unittest.mock import MagicMock
        user = MagicMock()
        user.id = 1
        user.telegram_id = 123456
        user.first_name = "Ivan"
        user.last_name = "Petrov"
        user.phone = "+998901234567"
        user.email = "ivan@test.com"
        user.language = "ru"
        user.status = "approved"
        user.verification_status = "approved"
        user.roles = '["executor","manager"]'
        user.role = "executor"
        user.active_role = "executor"

        profile = ProfileOut.from_user(user)
        assert profile.id == 1
        assert profile.roles == ["executor", "manager"]
        assert profile.active_role == "executor"

    def test_from_user_with_no_verification_status(self):
        """from_user handles missing verification_status attribute."""
        from unittest.mock import MagicMock
        user = MagicMock(spec=[
            "id", "telegram_id", "first_name", "last_name",
            "phone", "email", "language", "status", "roles", "role",
        ])
        user.id = 1
        user.telegram_id = 123456
        user.first_name = "A"
        user.last_name = "B"
        user.phone = None
        user.email = None
        user.language = "ru"
        user.status = "pending"
        user.roles = '["applicant"]'
        user.role = "applicant"

        profile = ProfileOut.from_user(user)
        assert profile.verification_status == "pending"
        assert profile.active_role is None


# ═══════════════════════ UpdateProfileBody ═══════════════════════


class TestUpdateProfileBody:

    def test_all_none(self):
        body = UpdateProfileBody()
        assert body.language is None
        assert body.email is None

    def test_with_language(self):
        body = UpdateProfileBody(language="uz")
        assert body.language == "uz"

    def test_with_email(self):
        body = UpdateProfileBody(email="new@example.com")
        assert body.email == "new@example.com"


# ═══════════════════════ RoleSwitchBody / RoleSwitchOut ═══════════════════════


class TestRoleSwitchModels:

    def test_role_switch_body(self):
        body = RoleSwitchBody(active_role="executor")
        assert body.active_role == "executor"

    def test_role_switch_body_missing_role_raises(self):
        with pytest.raises(ValidationError):
            RoleSwitchBody()

    def test_role_switch_out(self):
        out = RoleSwitchOut(active_role="manager", roles=["manager", "executor"])
        assert out.active_role == "manager"
        assert out.roles == ["manager", "executor"]

    def test_role_switch_out_missing_fields_raises(self):
        with pytest.raises(ValidationError):
            RoleSwitchOut(active_role="manager")
