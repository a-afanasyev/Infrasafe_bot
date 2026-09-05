from pydantic import BaseModel, field_validator, model_validator
from typing import Optional

from uk_management_bot.utils.constants import ACCEPTANCE_MODES, validate_canonical_urgency


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
    # Модуль «Лифты» (Ф4a-1, Р11): привязка к лифту — обязательна для категории
    # «лифт» при включённом флаге (validate_elevator_fields, как у TWA).
    elevator_id: Optional[int] = None
    elevator_operational: Optional[bool] = None
    # Кто принимает результат (Р3/Р9 — ремонт лифта из карточки: приёмка
    # менеджером). None → дефолт модели ('resident', как и раньше). Канон —
    # ACCEPTANCE_MODES (CHECK ck_requests_acceptance_mode).
    acceptance_mode: Optional[str] = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        # Та же валидация, что у applicant/inspector — менеджер не должен заводить
        # заявку с произвольной категорией (полонит Kanban/аналитику/webhook).
        from uk_management_bot.api.requests.schemas import _validate_request_category
        return _validate_request_category(v)

    @field_validator("urgency")
    @classmethod
    def validate_urgency(cls, v: str) -> str:
        # Толерантно (Phase 1): ключ ИЛИ legacy-рус → ключ; иначе ValueError.
        return validate_canonical_urgency(v)

    @field_validator("acceptance_mode")
    @classmethod
    def validate_acceptance_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ACCEPTANCE_MODES:
            raise ValueError(f"acceptance_mode must be one of: {list(ACCEPTANCE_MODES)}")
        return v

    @model_validator(mode="after")
    def _require_elevator_for_category(self):
        from uk_management_bot.api.requests.schemas import validate_elevator_fields
        validate_elevator_fields(self.category, self.elevator_id, self.elevator_operational)
        return self
