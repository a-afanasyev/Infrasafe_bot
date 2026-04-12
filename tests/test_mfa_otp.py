"""Tests for MFA OTP flow — service functions."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from uk_management_bot.api.auth.service import (
    create_mfa_token, verify_mfa_token, generate_otp,
    verify_otp, store_otp,
    MFA_TOKEN_EXPIRE_MINUTES, MFA_MAX_ATTEMPTS,
)


class TestMFAToken:
    def test_create_and_verify_roundtrip(self):
        token = create_mfa_token(user_id=42)
        user_id = verify_mfa_token(token)
        assert user_id == 42

    def test_verify_returns_none_for_garbage(self):
        assert verify_mfa_token("not.a.jwt") is None

    def test_verify_rejects_access_token(self):
        """An access token (purpose=None, aud set) must NOT pass as MFA token."""
        from uk_management_bot.api.auth.service import create_access_token
        access = create_access_token(user_id=1, roles=["manager"])
        assert verify_mfa_token(access) is None

    def test_verify_rejects_expired(self):
        from datetime import timedelta
        from jose import jwt
        from uk_management_bot.api.auth.service import SECRET_KEY, ALGORITHM
        from datetime import datetime, timezone
        payload = {
            "sub": "1",
            "purpose": "mfa",
            "exp": datetime.now(timezone.utc) - timedelta(seconds=10),
            "iss": "uk-management",
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        assert verify_mfa_token(token) is None


class TestGenerateOTP:
    def test_length_is_six(self):
        for _ in range(20):
            code = generate_otp()
            assert len(code) == 6
            assert code.isdigit()

    def test_different_codes(self):
        codes = {generate_otp() for _ in range(50)}
        assert len(codes) > 1  # not all identical


class TestVerifyOTP:
    @pytest.mark.asyncio
    async def test_valid_code_succeeds(self):
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {"code": "123456", "attempts": "3"}

        with patch("uk_management_bot.api.auth.service._get_redis", return_value=mock_redis):
            success, msg = await verify_otp(1, "123456")
            assert success is True
            assert msg == ""
            mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_code_decrements(self):
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {"code": "123456", "attempts": "3"}

        with patch("uk_management_bot.api.auth.service._get_redis", return_value=mock_redis):
            success, msg = await verify_otp(1, "000000")
            assert success is False
            assert "2" in msg  # 2 attempts remaining
            mock_redis.hincrby.assert_called_once()

    @pytest.mark.asyncio
    async def test_expired_otp_fails(self):
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {}

        with patch("uk_management_bot.api.auth.service._get_redis", return_value=mock_redis):
            success, msg = await verify_otp(1, "123456")
            assert success is False
            assert "expired" in msg.lower()

    @pytest.mark.asyncio
    async def test_zero_attempts_fails(self):
        mock_redis = AsyncMock()
        mock_redis.hgetall.return_value = {"code": "123456", "attempts": "0"}

        with patch("uk_management_bot.api.auth.service._get_redis", return_value=mock_redis):
            success, msg = await verify_otp(1, "123456")
            assert success is False
            assert "too many" in msg.lower()


class TestStoreOTP:
    @pytest.mark.asyncio
    async def test_stores_with_ttl(self):
        mock_redis = AsyncMock()

        with patch("uk_management_bot.api.auth.service._get_redis", return_value=mock_redis):
            await store_otp(42, "654321")
            mock_redis.hset.assert_called_once()
            mock_redis.expire.assert_called_once_with(
                "mfa:otp:42", MFA_TOKEN_EXPIRE_MINUTES * 60
            )
