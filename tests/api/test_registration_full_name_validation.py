"""SEC-109 — `RegisterApplicantIn.full_name` input hardening.

The registration WebApp POST is an HTTP path that bypasses the bot-side
`len(split) < 2` check. Without field constraints an attacker could persist a
multi-megabyte string or a bidi-control payload into users.first_name/last_name
(rendered in admin notifications). The schema now bounds length (2..200) and a
Unicode char-class pattern, with a validator rejecting whitespace-only.
"""
import pytest
from pydantic import ValidationError

from uk_management_bot.api.registration.schemas import RegisterApplicantIn


def _mk(full_name: str) -> RegisterApplicantIn:
    return RegisterApplicantIn(full_name=full_name, phone="+998901234567", apartment_id=1)


def test_valid_cyrillic_name_accepted():
    m = _mk("Иван Петров")
    assert m.full_name == "Иван Петров"


def test_valid_name_with_hyphen_and_apostrophe():
    assert _mk("Жан-Поль О'Коннор").full_name == "Жан-Поль О'Коннор"


def test_too_long_rejected():
    with pytest.raises(ValidationError):
        _mk("A" * 201)


def test_too_short_rejected():
    with pytest.raises(ValidationError):
        _mk("A")


def test_bidi_control_char_rejected():
    # U+202E RIGHT-TO-LEFT OVERRIDE — classic spoofing payload.
    with pytest.raises(ValidationError):
        _mk("‮admin payload")


def test_whitespace_only_rejected():
    with pytest.raises(ValidationError):
        _mk("   ")


def test_null_byte_rejected():
    with pytest.raises(ValidationError):
        _mk("Ivan\x00")


def test_angle_brackets_rejected():
    # HTML/script-ish payload — '<' '>' are outside the allowed class.
    with pytest.raises(ValidationError):
        _mk("<script>alert(1)</script>")
