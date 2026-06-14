"""Unit tests for uk_management_bot/api/auth/service.py pure functions."""
import hashlib
import hmac
import time
from datetime import timedelta
from unittest.mock import patch


# Patch settings before importing service so SECRET_KEY initialises cleanly
with patch.dict(
    "os.environ",
    {
        "DEBUG": "True",
        "BOT_TOKEN": "test_bot_token:test",
        "ADMIN_PASSWORD": "dev_password_change_me",
        "INVITE_SECRET": "test-invite-secret",
        "JWT_SECRET": "test-jwt-secret",
    },
):
    from uk_management_bot.api.auth.service import (
        hash_password,
        verify_password,
        create_access_token,
        verify_access_token,
        create_refresh_token_value,
        hash_token,
        verify_telegram_widget,
        verify_twa_init_data,
        AUTH_DATE_MAX_AGE_SECONDS,
    )


# ---------------------------------------------------------------------------
# hash_password / verify_password
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_hash_then_verify_returns_true(self):
        hashed = hash_password("secret123")
        assert verify_password("secret123", hashed) is True

    def test_wrong_password_returns_false(self):
        hashed = hash_password("secret123")
        assert verify_password("wrongpassword", hashed) is False

    def test_different_hashes_for_same_password(self):
        """bcrypt uses random salt — each hash must differ."""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2

    def test_hash_is_string(self):
        assert isinstance(hash_password("abc"), str)


# ---------------------------------------------------------------------------
# create_access_token / verify_access_token
# ---------------------------------------------------------------------------

class TestAccessToken:
    def test_create_then_verify_returns_payload(self):
        token = create_access_token(user_id=1, roles=["applicant"])
        payload = verify_access_token(token)
        assert payload is not None
        assert payload["sub"] == "1"
        assert payload["roles"] == ["applicant"]

    def test_create_with_multiple_roles(self):
        token = create_access_token(user_id=42, roles=["manager", "executor"])
        payload = verify_access_token(token)
        assert payload["sub"] == "42"
        assert "manager" in payload["roles"]
        assert "executor" in payload["roles"]

    def test_invalid_token_returns_none(self):
        result = verify_access_token("this.is.not.a.valid.token")
        assert result is None

    def test_tampered_token_returns_none(self):
        token = create_access_token(user_id=5, roles=["applicant"])
        tampered = token[:-4] + "xxxx"
        assert verify_access_token(tampered) is None

    def test_expired_token_returns_none(self):
        token = create_access_token(
            user_id=7, roles=["applicant"], expires_delta=timedelta(seconds=-1)
        )
        assert verify_access_token(token) is None

    def test_empty_string_returns_none(self):
        assert verify_access_token("") is None


# ---------------------------------------------------------------------------
# create_refresh_token_value
# ---------------------------------------------------------------------------

class TestRefreshTokenValue:
    def test_returns_64_char_hex_string(self):
        value = create_refresh_token_value()
        assert isinstance(value, str)
        assert len(value) == 64
        # valid hex
        int(value, 16)

    def test_tokens_are_unique(self):
        assert create_refresh_token_value() != create_refresh_token_value()


# ---------------------------------------------------------------------------
# hash_token
# ---------------------------------------------------------------------------

class TestHashToken:
    def test_returns_sha256_hex(self):
        token = "some-refresh-token"
        result = hash_token(token)
        expected = hashlib.sha256(token.encode()).hexdigest()
        assert result == expected

    def test_returns_64_char_string(self):
        assert len(hash_token("anything")) == 64

    def test_deterministic(self):
        assert hash_token("abc") == hash_token("abc")

    def test_different_inputs_differ(self):
        assert hash_token("abc") != hash_token("xyz")


# ---------------------------------------------------------------------------
# verify_telegram_widget
# ---------------------------------------------------------------------------

def _make_widget_data(bot_token: str, extra: dict | None = None) -> dict:
    """Build a correctly-signed Telegram Widget login payload."""
    data: dict = {"id": "123456", "first_name": "Test"}
    if extra:
        data.update(extra)
    data["auth_date"] = str(int(time.time()))
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    data["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return data


class TestVerifyTelegramWidget:
    BOT_TOKEN = "test_bot_token:test"

    def test_valid_data_returns_true(self):
        data = _make_widget_data(self.BOT_TOKEN)
        with patch("uk_management_bot.api.auth.service.settings") as mock_settings:
            mock_settings.BOT_TOKEN = self.BOT_TOKEN
            assert verify_telegram_widget(data) is True

    def test_missing_hash_returns_false(self):
        data = {"id": "123456", "auth_date": str(int(time.time()))}
        # no hash key
        with patch("uk_management_bot.api.auth.service.settings") as mock_settings:
            mock_settings.BOT_TOKEN = self.BOT_TOKEN
            assert verify_telegram_widget(data) is False

    def test_wrong_hash_returns_false(self):
        data = _make_widget_data(self.BOT_TOKEN)
        data["hash"] = "deadbeef" * 8  # 64 chars but wrong
        with patch("uk_management_bot.api.auth.service.settings") as mock_settings:
            mock_settings.BOT_TOKEN = self.BOT_TOKEN
            assert verify_telegram_widget(data) is False

    def test_expired_auth_date_returns_false(self):
        data = _make_widget_data(self.BOT_TOKEN)
        data["auth_date"] = str(int(time.time()) - AUTH_DATE_MAX_AGE_SECONDS - 1)
        # Recompute hash with the stale auth_date
        data.pop("hash")
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret_key = hashlib.sha256(self.BOT_TOKEN.encode()).digest()
        data["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        with patch("uk_management_bot.api.auth.service.settings") as mock_settings:
            mock_settings.BOT_TOKEN = self.BOT_TOKEN
            assert verify_telegram_widget(data) is False

    def test_does_not_mutate_input(self):
        """verify_telegram_widget must not pop 'hash' from the caller's dict."""
        data = _make_widget_data(self.BOT_TOKEN)
        original_hash = data["hash"]
        with patch("uk_management_bot.api.auth.service.settings") as mock_settings:
            mock_settings.BOT_TOKEN = self.BOT_TOKEN
            verify_telegram_widget(data)
        assert data.get("hash") == original_hash


# ---------------------------------------------------------------------------
# verify_twa_init_data
# ---------------------------------------------------------------------------

def _make_twa_init_data(bot_token: str, user_json: str = '{"id":1,"first_name":"Test"}') -> str:
    """Build a correctly-signed TWA initData query string."""
    import urllib.parse
    params = {"user": urllib.parse.quote(user_json), "auth_date": str(int(time.time()))}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(params)


class TestVerifyTwaInitData:
    BOT_TOKEN = "test_bot_token:test"

    def test_valid_init_data_returns_user_dict(self):
        init_data = _make_twa_init_data(self.BOT_TOKEN)
        result = verify_twa_init_data(init_data, self.BOT_TOKEN)
        assert result is not None
        assert result.get("id") == 1
        assert result.get("first_name") == "Test"

    def test_missing_hash_returns_none(self):
        result = verify_twa_init_data("auth_date=1234567890&user=%7B%7D", self.BOT_TOKEN)
        assert result is None

    def test_wrong_hash_returns_none(self):
        init_data = _make_twa_init_data(self.BOT_TOKEN)
        # Replace hash with an invalid one
        init_data = "&".join(
            part if not part.startswith("hash=") else "hash=deadbeefdeadbeef"
            for part in init_data.split("&")
        )
        result = verify_twa_init_data(init_data, self.BOT_TOKEN)
        assert result is None

    def test_empty_string_returns_none(self):
        assert verify_twa_init_data("", self.BOT_TOKEN) is None
