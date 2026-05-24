from pydantic import BaseModel, field_validator
from typing import Optional, List, Literal
from datetime import datetime

VALID_STATUSES = [
    "Новая", "В работе", "Закуп", "Уточнение",
    "Выполнена", "Исполнено", "Принято", "Отменена",
]
VALID_URGENCIES = ["Обычная", "Средняя", "Срочная", "Критическая"]


class RequestCard(BaseModel):
    request_number: str
    status: str
    category: str
    urgency: Optional[str] = None
    source: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    apartment_id: Optional[int] = None
    executor_id: Optional[int] = None
    executor_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    manager_confirmed: bool = False
    completion_report: Optional[str] = None
    notes: Optional[str] = None
    requested_materials: Optional[str] = None
    return_reason: Optional[str] = None
    # INT-120 #3 — Sprint 10 reopen-chain metadata, surfaced on the detail
    # endpoint only (GET /api/v2/requests/{number}). Populated from the
    # accepted webhook_inbox row when the request was created via inbound
    # InfraSafe alert. Sequence=1 (deployed-wire first-time default) is
    # treated as «no reopen» and returned as None.
    reopen_sequence: Optional[int] = None
    reopen_chain_id: Optional[str] = None
    related_request_number: Optional[str] = None
    engineer_required_reason: Optional[str] = None

    model_config = {"from_attributes": True}


class KanbanColumn(BaseModel):
    status: str
    count: int
    requests: List[RequestCard]


class KanbanResponse(BaseModel):
    columns: List[KanbanColumn]


class CreateRequestBody(BaseModel):
    category: str
    urgency: str
    description: str
    apartment_id: Optional[int] = None
    address: Optional[str] = None
    source: str = "web"
    media_files: Optional[List[str]] = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        from uk_management_bot.config.settings import settings
        valid = settings.REQUEST_CATEGORIES
        if v not in valid:
            raise ValueError(f"category must be one of: {valid}")
        return v

    @field_validator("urgency")
    @classmethod
    def validate_urgency(cls, v: str) -> str:
        if v not in VALID_URGENCIES:
            raise ValueError(f"urgency must be one of: {VALID_URGENCIES}")
        return v


class UpdateRequestBody(BaseModel):
    status: Optional[str] = None
    executor_id: Optional[int] = None
    notes: Optional[str] = None
    completion_report: Optional[str] = None
    manager_confirmed: Optional[bool] = None
    manager_confirmation_notes: Optional[str] = None
    requested_materials: Optional[str] = None
    return_reason: Optional[str] = None
    rating: Optional[int] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_STATUSES:
            raise ValueError(f"status must be one of: {VALID_STATUSES}")
        return v

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and (not isinstance(v, int) or v < 1 or v > 5):
            raise ValueError("rating must be an integer between 1 and 5")
        return v


class CommentBody(BaseModel):
    text: str
    is_internal: bool = False
    media_files: Optional[List[str]] = None


class CommentOut(BaseModel):
    id: int
    user_id: int
    comment_type: str
    comment_text: str
    is_internal: bool = False
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
