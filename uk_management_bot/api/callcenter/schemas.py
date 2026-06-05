from pydantic import BaseModel, field_validator
from typing import Optional

from uk_management_bot.utils.constants import validate_canonical_urgency


class ResidentSearchResult(BaseModel):
    id: int
    telegram_id: int
    full_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    requests_count: int = 0

    model_config = {"from_attributes": True}


class CallCenterCreateRequest(BaseModel):
    category: str
    urgency: str
    description: str
    user_id: Optional[int] = None
    apartment_id: Optional[int] = None
    caller_name: Optional[str] = None
    caller_phone: Optional[str] = None
    address: Optional[str] = None

    @field_validator("urgency")
    @classmethod
    def validate_urgency(cls, v: str) -> str:
        # Толерантно (Phase 1): ключ ИЛИ legacy-рус → ключ; иначе ValueError.
        return validate_canonical_urgency(v)
