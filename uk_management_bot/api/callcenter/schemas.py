from pydantic import BaseModel
from typing import Optional


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
