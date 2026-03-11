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
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    manager_confirmed: bool = False

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

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_STATUSES:
            raise ValueError(f"status must be one of: {VALID_STATUSES}")
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
