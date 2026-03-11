import pytest
from datetime import timedelta
from uk_management_bot.api.auth.service import (
    create_access_token, verify_access_token,
    hash_password, verify_password,
    verify_twa_init_data,
)


def test_access_token_roundtrip():
    token = create_access_token(user_id=42, roles=["manager"])
    payload = verify_access_token(token)
    assert payload["sub"] == "42"
    assert payload["roles"] == ["manager"]


def test_expired_token_returns_none():
    token = create_access_token(user_id=1, roles=["applicant"], expires_delta=timedelta(seconds=-1))
    assert verify_access_token(token) is None


def test_password_hash_and_verify():
    hashed = hash_password("MySecret123")
    assert verify_password("MySecret123", hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_twa_init_data_invalid_hash():
    result = verify_twa_init_data("user=%7B%22id%22%3A123%7D&hash=badhash", "fake_bot_token")
    assert result is None
