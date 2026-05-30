from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


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
    full_name: str = Field(..., min_length=1, max_length=255)
    phone: str = Field(..., min_length=1, max_length=20)
    apartment_id: int


class RegistrationResult(BaseModel):
    status: str  # always "pending"
