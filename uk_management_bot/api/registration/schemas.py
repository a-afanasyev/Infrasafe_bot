from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field, field_validator

# SEC-109: name char-class — Unicode letters/numbers, whitespace, and the
# punctuation real names use (hyphen, apostrophe, dot). Compiled by
# pydantic-core's Rust regex engine, which supports \p{L}/\p{N}. Rejects bidi
# control chars (Cf, e.g. U+202E) and any other control/format characters that
# would otherwise be persisted into users.first_name/last_name and rendered in
# admin notifications.
_FULL_NAME_PATTERN = r"^[\p{L}\p{N}\s\-'\.]+$"


class StartIn(BaseModel):
    init_data: str = Field(..., min_length=1)


class ApartmentOut(BaseModel):
    id: int
    yard_name: Optional[str] = None
    building_address: Optional[str] = None
    apartment_number: str


class Prefill(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None


class StartOut(BaseModel):
    registration_ticket: str
    prefill: Prefill
    apartments: list[ApartmentOut]


class RegisterApplicantIn(BaseModel):
    full_name: str = Field(
        ..., min_length=2, max_length=200, pattern=_FULL_NAME_PATTERN
    )
    phone: str = Field(..., min_length=1, max_length=20)
    apartment_id: int

    @field_validator("full_name")
    @classmethod
    def _full_name_not_blank(cls, v: str) -> str:
        # The pattern admits all-whitespace ("\s" is in the class), which would
        # pass min_length=2 yet break router .split()[0] (IndexError → 500).
        # Reject whitespace-only here so the API answers 422, not 500.
        if not v.strip():
            raise ValueError("full_name must not be blank")
        return v


class RegistrationResult(BaseModel):
    status: str  # always "pending"
