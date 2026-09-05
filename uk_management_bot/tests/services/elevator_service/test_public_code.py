"""Юнит-тесты публичного кода лифта (Ф2a)."""
import re

import pytest

from uk_management_bot.services.elevator_service import (
    PUBLIC_CODE_MAX_LEN,
    generate_public_code,
    is_valid_public_code,
)

pytestmark = pytest.mark.unit

ALPHABET = re.compile(r"^[A-Za-z0-9_-]+$")


def test_length_and_alphabet():
    for _ in range(100):
        code = generate_public_code()
        assert 16 <= len(code) <= PUBLIC_CODE_MAX_LEN
        assert ALPHABET.match(code)
        assert is_valid_public_code(code)


def test_unique_over_1000():
    codes = {generate_public_code() for _ in range(1000)}
    assert len(codes) == 1000


def test_max_len_matches_column():
    assert PUBLIC_CODE_MAX_LEN == 32


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "short",
        "a" * 33,
        "with space here 1234",
        "плохой_код_кириллица",
        "a/b" * 8,
        "abc=abc=abc=abc=abc=",
        None,
        123,
    ],
)
def test_invalid_codes(bad):
    assert is_valid_public_code(bad) is False  # type: ignore[arg-type]


def test_valid_boundaries():
    assert is_valid_public_code("a" * 16) is True
    assert is_valid_public_code("Z-_9" * 8) is True
