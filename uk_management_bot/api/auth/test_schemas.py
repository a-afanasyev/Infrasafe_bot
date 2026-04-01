"""
Unit tests for api/auth/schemas.py

Tests Pydantic validation for TokenResponse, TelegramWidgetLogin, TWALogin,
PasswordLogin, RefreshRequest, SetPasswordRequest.
"""
import pytest

from uk_management_bot.api.auth.schemas import (
    TokenResponse,
    TelegramWidgetLogin,
    TWALogin,
    PasswordLogin,
    RefreshRequest,
    SetPasswordRequest,
)


# ---------------------------------------------------------------------------
# TokenResponse
# ---------------------------------------------------------------------------

class TestTokenResponse:
    def test_valid(self):
        resp = TokenResponse(
            access_token="access.jwt.token",
            refresh_token="refresh.jwt.token",
        )
        assert resp.token_type == "bearer"

    def test_all_fields(self):
        resp = TokenResponse(
            access_token="a",
            refresh_token="r",
            token_type="bearer",
        )
        assert resp.access_token == "a"
        assert resp.refresh_token == "r"
        assert resp.token_type == "bearer"

    def test_token_type_default_bearer(self):
        resp = TokenResponse(access_token="a", refresh_token="r")
        assert resp.token_type == "bearer"

    def test_missing_access_token_raises(self):
        with pytest.raises(Exception):
            TokenResponse(refresh_token="r")

    def test_missing_refresh_token_raises(self):
        with pytest.raises(Exception):
            TokenResponse(access_token="a")


# ---------------------------------------------------------------------------
# TelegramWidgetLogin
# ---------------------------------------------------------------------------

class TestTelegramWidgetLogin:
    def _base(self, **overrides) -> dict:
        base = {
            "id": 123456789,
            "first_name": "Ivan",
            "auth_date": 1700000000,
            "hash": "abc123def456",
        }
        base.update(overrides)
        return base

    def test_valid_minimal(self):
        login = TelegramWidgetLogin(**self._base())
        assert login.id == 123456789
        assert login.last_name is None
        assert login.username is None
        assert login.photo_url is None

    def test_full_payload(self):
        login = TelegramWidgetLogin(**self._base(
            last_name="Petrov",
            username="ivanpetrov",
            photo_url="https://example.com/photo.jpg",
        ))
        assert login.last_name == "Petrov"
        assert login.username == "ivanpetrov"

    def test_missing_id_raises(self):
        data = self._base()
        del data["id"]
        with pytest.raises(Exception):
            TelegramWidgetLogin(**data)

    def test_missing_first_name_raises(self):
        data = self._base()
        del data["first_name"]
        with pytest.raises(Exception):
            TelegramWidgetLogin(**data)

    def test_missing_auth_date_raises(self):
        data = self._base()
        del data["auth_date"]
        with pytest.raises(Exception):
            TelegramWidgetLogin(**data)

    def test_missing_hash_raises(self):
        data = self._base()
        del data["hash"]
        with pytest.raises(Exception):
            TelegramWidgetLogin(**data)


# ---------------------------------------------------------------------------
# TWALogin
# ---------------------------------------------------------------------------

class TestTWALogin:
    def test_valid(self):
        login = TWALogin(init_data="user=...&hash=...")
        assert login.init_data == "user=...&hash=..."

    def test_missing_init_data_raises(self):
        with pytest.raises(Exception):
            TWALogin()

    def test_empty_string_accepted(self):
        """Pydantic does not validate non-empty for plain str fields by default."""
        login = TWALogin(init_data="")
        assert login.init_data == ""


# ---------------------------------------------------------------------------
# PasswordLogin
# ---------------------------------------------------------------------------

class TestPasswordLogin:
    def test_valid(self):
        login = PasswordLogin(email="admin@example.com", password="secret")
        assert login.email == "admin@example.com"
        assert login.password == "secret"

    def test_missing_email_raises(self):
        with pytest.raises(Exception):
            PasswordLogin(password="secret")

    def test_missing_password_raises(self):
        with pytest.raises(Exception):
            PasswordLogin(email="admin@example.com")

    def test_both_required(self):
        with pytest.raises(Exception):
            PasswordLogin()


# ---------------------------------------------------------------------------
# RefreshRequest
# ---------------------------------------------------------------------------

class TestRefreshRequest:
    def test_valid(self):
        req = RefreshRequest(refresh_token="my.refresh.token")
        assert req.refresh_token == "my.refresh.token"

    def test_missing_refresh_token_raises(self):
        with pytest.raises(Exception):
            RefreshRequest()


# ---------------------------------------------------------------------------
# SetPasswordRequest
# ---------------------------------------------------------------------------

class TestSetPasswordRequest:
    def test_valid(self):
        req = SetPasswordRequest(password="newPass123", confirm_password="newPass123")
        assert req.password == "newPass123"
        assert req.confirm_password == "newPass123"

    def test_missing_password_raises(self):
        with pytest.raises(Exception):
            SetPasswordRequest(confirm_password="abc")

    def test_missing_confirm_password_raises(self):
        with pytest.raises(Exception):
            SetPasswordRequest(password="abc")

    def test_passwords_can_differ(self):
        """Schema does not enforce match — that is a business-logic concern in the router."""
        req = SetPasswordRequest(password="abc", confirm_password="xyz")
        assert req.password == "abc"
        assert req.confirm_password == "xyz"

    def test_both_required(self):
        with pytest.raises(Exception):
            SetPasswordRequest()
