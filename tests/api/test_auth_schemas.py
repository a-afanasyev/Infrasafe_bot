"""Tests for auth Pydantic schemas (uk_management_bot/api/auth/schemas.py)."""
import pytest
from pydantic import ValidationError

from uk_management_bot.api.auth.schemas import (
    TokenResponse,
    TelegramWidgetLogin,
    TWALogin,
    PasswordLogin,
    RefreshRequest,
    SetPasswordRequest,
)


# ═══════════════════════ TokenResponse ═══════════════════════


class TestTokenResponse:

    def test_valid_with_defaults(self):
        resp = TokenResponse(access_token="abc", refresh_token="xyz")
        assert resp.access_token == "abc"
        assert resp.refresh_token == "xyz"
        assert resp.token_type == "bearer"

    def test_custom_token_type(self):
        resp = TokenResponse(access_token="a", refresh_token="b", token_type="custom")
        assert resp.token_type == "custom"

    def test_missing_access_token_raises(self):
        with pytest.raises(ValidationError):
            TokenResponse(refresh_token="xyz")

    def test_missing_refresh_token_raises(self):
        with pytest.raises(ValidationError):
            TokenResponse(access_token="abc")


# ═══════════════════════ TelegramWidgetLogin ═══════════════════════


class TestTelegramWidgetLogin:

    def test_valid_minimal(self):
        login = TelegramWidgetLogin(
            id=12345, first_name="Ivan", auth_date=1700000000, hash="abc123"
        )
        assert login.id == 12345
        assert login.first_name == "Ivan"
        assert login.last_name is None
        assert login.username is None
        assert login.photo_url is None

    def test_valid_full(self):
        login = TelegramWidgetLogin(
            id=12345,
            first_name="Ivan",
            last_name="Petrov",
            username="ipetrov",
            photo_url="https://t.me/photo.jpg",
            auth_date=1700000000,
            hash="abc123",
        )
        assert login.last_name == "Petrov"
        assert login.username == "ipetrov"
        assert login.photo_url == "https://t.me/photo.jpg"

    def test_missing_id_raises(self):
        with pytest.raises(ValidationError):
            TelegramWidgetLogin(first_name="Ivan", auth_date=1700000000, hash="abc")

    def test_missing_first_name_raises(self):
        with pytest.raises(ValidationError):
            TelegramWidgetLogin(id=1, auth_date=1700000000, hash="abc")

    def test_missing_auth_date_raises(self):
        with pytest.raises(ValidationError):
            TelegramWidgetLogin(id=1, first_name="Ivan", hash="abc")

    def test_missing_hash_raises(self):
        with pytest.raises(ValidationError):
            TelegramWidgetLogin(id=1, first_name="Ivan", auth_date=1700000000)


# ═══════════════════════ TWALogin ═══════════════════════


class TestTWALogin:

    def test_valid(self):
        login = TWALogin(init_data="user=%7B%22id%22%3A123%7D&hash=abc")
        assert login.init_data == "user=%7B%22id%22%3A123%7D&hash=abc"

    def test_missing_init_data_raises(self):
        with pytest.raises(ValidationError):
            TWALogin()


# ═══════════════════════ PasswordLogin ═══════════════════════


class TestPasswordLogin:

    def test_valid(self):
        login = PasswordLogin(email="admin@example.com", password="secret123")
        assert login.email == "admin@example.com"
        assert login.password == "secret123"

    def test_missing_email_raises(self):
        with pytest.raises(ValidationError):
            PasswordLogin(password="secret")

    def test_missing_password_raises(self):
        with pytest.raises(ValidationError):
            PasswordLogin(email="admin@example.com")


# ═══════════════════════ RefreshRequest ═══════════════════════


class TestRefreshRequest:

    def test_valid(self):
        req = RefreshRequest(refresh_token="tok_abc")
        assert req.refresh_token == "tok_abc"

    def test_missing_token_raises(self):
        with pytest.raises(ValidationError):
            RefreshRequest()


# ═══════════════════════ SetPasswordRequest ═══════════════════════


class TestSetPasswordRequest:

    def test_valid(self):
        req = SetPasswordRequest(password="newpass123", confirm_password="newpass123")
        assert req.password == "newpass123"
        assert req.confirm_password == "newpass123"

    def test_missing_password_raises(self):
        with pytest.raises(ValidationError):
            SetPasswordRequest(confirm_password="x")

    def test_missing_confirm_password_raises(self):
        with pytest.raises(ValidationError):
            SetPasswordRequest(password="x")
