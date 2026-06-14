"""Extended tests for auth service (uk_management_bot/api/auth/service.py).

The basic roundtrip and expiry tests are in test_auth_service.py.
This file adds coverage for edge cases, helper functions, and verification logic.
"""
import hashlib
import hmac
import json
import time
from datetime import timedelta
from urllib.parse import urlencode

import pytest

from uk_management_bot.api.auth.service import (
    create_access_token,
    verify_access_token,
    hash_password,
    verify_password,
    create_refresh_token_value,
    hash_token,
    verify_telegram_widget,
    verify_twa_init_data,
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    AUTH_DATE_MAX_AGE_SECONDS,
)
from uk_management_bot.config.settings import settings


# ═══════════════════════ Module-level constants ═══════════════════════


class TestConstants:

    def test_algorithm_is_hs256(self):
        assert ALGORITHM == "HS256"

    def test_access_token_expire_minutes_is_positive(self):
        assert ACCESS_TOKEN_EXPIRE_MINUTES > 0

    def test_refresh_token_expire_days_is_positive(self):
        assert REFRESH_TOKEN_EXPIRE_DAYS > 0

    def test_auth_date_max_age_is_5min(self):
        # Plan §7.4: tightened from 86400 (24h) to 300s to kill widget-hash replay.
        assert AUTH_DATE_MAX_AGE_SECONDS == 300

    def test_secret_key_is_set(self):
        assert SECRET_KEY is not None
        assert len(SECRET_KEY) > 0


# ═══════════════════════ Token creation/verification ═══════════════════════


class TestTokenCreation:

    def test_token_contains_sub_and_roles(self):
        token = create_access_token(user_id=99, roles=["manager", "executor"])
        payload = verify_access_token(token)
        assert payload is not None
        assert payload["sub"] == "99"
        assert payload["roles"] == ["manager", "executor"]
        assert "exp" in payload

    def test_token_with_empty_roles(self):
        token = create_access_token(user_id=1, roles=[])
        payload = verify_access_token(token)
        assert payload["roles"] == []

    def test_token_with_custom_expiry(self):
        token = create_access_token(
            user_id=1, roles=["applicant"],
            expires_delta=timedelta(hours=2),
        )
        payload = verify_access_token(token)
        assert payload is not None

    def test_expired_token_returns_none(self):
        token = create_access_token(
            user_id=1, roles=["applicant"],
            expires_delta=timedelta(seconds=-10),
        )
        assert verify_access_token(token) is None

    def test_invalid_token_string_returns_none(self):
        assert verify_access_token("not.a.valid.token") is None

    def test_empty_token_returns_none(self):
        assert verify_access_token("") is None

    def test_tampered_token_returns_none(self):
        token = create_access_token(user_id=1, roles=["applicant"])
        # Tamper a character in the MIDDLE of the signature segment. Flipping
        # the LAST base64 char is non-deterministic: trailing bits can be
        # redundant, so the mutated char may decode to the same signature bytes
        # → token still valid → flaky failure. A middle char always maps to
        # real bytes, so the signature is guaranteed to change.
        header, payload, sig = token.split(".")
        i = len(sig) // 2
        sig = sig[:i] + ("A" if sig[i] != "A" else "B") + sig[i + 1:]
        tampered = ".".join([header, payload, sig])
        assert verify_access_token(tampered) is None


# ═══════════════════════ Password hashing ═══════════════════════


class TestPasswordHashing:

    def test_hash_is_different_from_plaintext(self):
        hashed = hash_password("MySecret")
        assert hashed != "MySecret"

    def test_verify_correct_password(self):
        hashed = hash_password("Correct123")
        assert verify_password("Correct123", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("Correct123")
        assert verify_password("Wrong456", hashed) is False

    def test_different_hashes_for_same_password(self):
        """bcrypt uses random salt, so same password produces different hashes."""
        h1 = hash_password("Same")
        h2 = hash_password("Same")
        assert h1 != h2
        # Both should verify
        assert verify_password("Same", h1) is True
        assert verify_password("Same", h2) is True


# ═══════════════════════ Refresh token / hash_token ═══════════════════════


class TestRefreshTokenHelpers:

    def test_create_refresh_token_value_is_hex(self):
        val = create_refresh_token_value()
        assert isinstance(val, str)
        assert len(val) == 64  # 32 bytes = 64 hex chars
        int(val, 16)  # Should not raise

    def test_create_refresh_token_values_are_unique(self):
        vals = {create_refresh_token_value() for _ in range(10)}
        assert len(vals) == 10  # All unique

    def test_hash_token_is_sha256(self):
        result = hash_token("test_value")
        expected = hashlib.sha256("test_value".encode()).hexdigest()
        assert result == expected

    def test_hash_token_deterministic(self):
        assert hash_token("abc") == hash_token("abc")

    def test_hash_token_different_inputs(self):
        assert hash_token("abc") != hash_token("def")


# ═══════════════════════ verify_telegram_widget ═══════════════════════


class TestVerifyTelegramWidget:

    def _build_valid_data(self) -> dict:
        """Build data that passes Telegram Widget verification."""
        auth_date = str(int(time.time()))
        data = {
            "id": "123",
            "first_name": "Ivan",
            "auth_date": auth_date,
        }
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret_key = hashlib.sha256(settings.BOT_TOKEN.encode()).digest()
        expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        data["hash"] = expected_hash
        return data

    def test_missing_hash_returns_false(self):
        data = {"id": "123", "first_name": "Ivan", "auth_date": str(int(time.time()))}
        assert verify_telegram_widget(data) is False

    def test_wrong_hash_returns_false(self):
        data = {
            "id": "123", "first_name": "Ivan",
            "auth_date": str(int(time.time())), "hash": "wrong",
        }
        assert verify_telegram_widget(data) is False

    def test_expired_auth_date_returns_false(self):
        old_time = str(int(time.time()) - AUTH_DATE_MAX_AGE_SECONDS - 100)
        data = {
            "id": "123", "first_name": "Ivan",
            "auth_date": old_time, "hash": "somehash",
        }
        assert verify_telegram_widget(data) is False

    def test_invalid_auth_date_returns_false(self):
        data = {
            "id": "123", "first_name": "Ivan",
            "auth_date": "not_a_number", "hash": "somehash",
        }
        assert verify_telegram_widget(data) is False

    def test_does_not_mutate_input(self):
        data = {"id": "123", "first_name": "Ivan", "auth_date": "1", "hash": "abc"}
        original = dict(data)
        verify_telegram_widget(data)
        assert data == original

    def test_valid_data_returns_true(self):
        if not settings.BOT_TOKEN:
            pytest.skip("BOT_TOKEN not set")
        data = self._build_valid_data()
        assert verify_telegram_widget(data) is True


# ═══════════════════════ verify_twa_init_data ═══════════════════════


class TestVerifyTwaInitData:

    def _build_valid_init_data(self, bot_token: str) -> str:
        """Build initData string that passes TWA verification."""
        auth_date = str(int(time.time()))
        user_data = json.dumps({"id": 123, "first_name": "Ivan"})
        params = {"auth_date": auth_date, "user": user_data}
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        params["hash"] = expected_hash
        return urlencode(params)

    def test_missing_hash_returns_none(self):
        result = verify_twa_init_data("user=%7B%22id%22%3A123%7D", "token")
        assert result is None

    def test_wrong_hash_returns_none(self):
        result = verify_twa_init_data("user=%7B%22id%22%3A123%7D&hash=wrong", "token")
        assert result is None

    def test_expired_auth_date_returns_none(self):
        old_time = str(int(time.time()) - AUTH_DATE_MAX_AGE_SECONDS - 100)
        init_data = f"auth_date={old_time}&hash=somehash"
        result = verify_twa_init_data(init_data, "token")
        assert result is None

    def test_invalid_auth_date_returns_none(self):
        init_data = "auth_date=not_a_number&hash=somehash"
        result = verify_twa_init_data(init_data, "token")
        assert result is None

    def test_valid_data_returns_user_dict(self):
        bot_token = "fake_bot_token_for_test"
        init_data = self._build_valid_init_data(bot_token)
        result = verify_twa_init_data(init_data, bot_token)
        assert result is not None
        assert result["id"] == 123
        assert result["first_name"] == "Ivan"

    def test_valid_data_without_user_returns_parsed(self):
        """When there is no 'user' field, returns the parsed dict."""
        bot_token = "test_token"
        auth_date = str(int(time.time()))
        params = {"auth_date": auth_date, "some_field": "value"}
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        params["hash"] = expected_hash
        init_data = urlencode(params)

        result = verify_twa_init_data(init_data, bot_token)
        assert result is not None
        assert result["some_field"] == "value"

    def test_invalid_user_json_returns_none(self):
        """When user field contains invalid JSON, returns None."""
        bot_token = "test_token"
        auth_date = str(int(time.time()))
        params = {"auth_date": auth_date, "user": "not-json"}
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        params["hash"] = expected_hash
        init_data = urlencode(params)

        result = verify_twa_init_data(init_data, bot_token)
        assert result is None
