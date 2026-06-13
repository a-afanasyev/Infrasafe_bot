from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, List, Literal
from datetime import datetime

from uk_management_bot.utils.constants import URGENCY_VALUES, validate_canonical_urgency

VALID_STATUSES = [
    "Новая", "В работе", "Закуп", "Уточнение",
    "Выполнена", "Исполнено", "Принято", "Отменена",
]
# Канон — ключи (low/medium/high/critical); валидация толерантна (см. validate_canonical_urgency).
VALID_URGENCIES = list(URGENCY_VALUES)


class RequestCard(BaseModel):
    request_number: str
    status: str
    category: str
    urgency: Optional[str] = None
    source: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    apartment_id: Optional[int] = None
    # 3-уровневый структурированный адрес (план «Обходчик»).
    building_id: Optional[int] = None
    yard_id: Optional[int] = None
    address_type: Optional[str] = None
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
    # FE-119 — InfraSafe alert context (metric + infrastructure), surfaced on
    # the detail endpoint from webhook_inbox.payload.alert. All optional / render
    # -if-present: boolean alerts (LEAK_DETECTED) carry metric_label only, no
    # value/range; numeric alerts (transformer/heating/voltage) carry the full
    # set. metric_normal_* is the working threshold band (alert fires outside it),
    # one-sided when only min OR max is present (e.g. heating ≥40).
    metric_label: Optional[str] = None
    metric_value: Optional[float] = None
    metric_unit: Optional[str] = None
    metric_normal_min: Optional[float] = None
    metric_normal_max: Optional[float] = None
    infrastructure_label: Optional[str] = None

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _project_address_type(self) -> "RequestCard":
        # Defensive-coalesce: если address_type не задан (немигрированная/legacy
        # строка), проецируем его по заполненному FK — иначе старые квартирные
        # заявки показались бы как legacy. Контракт карточки стабилен сразу.
        if self.address_type is None:
            if self.apartment_id is not None:
                self.address_type = "apartment"
            elif self.building_id is not None:
                self.address_type = "building"
            elif self.yard_id is not None:
                self.address_type = "yard"
            else:
                self.address_type = "legacy"
        return self


class KanbanColumn(BaseModel):
    status: str
    count: int
    requests: List[RequestCard]


class KanbanResponse(BaseModel):
    columns: List[KanbanColumn]


def _validate_request_category(v: str) -> str:
    from uk_management_bot.config.settings import settings
    valid = settings.REQUEST_CATEGORIES
    if v not in valid:
        raise ValueError(f"category must be one of: {valid}")
    return v


class CreateRequestBody(BaseModel):
    """Структурный контракт жителя (план «Обходчик», пилот — один шаг).

    Клиент передаёт уровень + id записи; адрес/FK/source считает сервер через
    resolve_request_address. Legacy-поля (apartment_id/address/source в body)
    исключены — под пилот без переходного окна.
    """

    category: str
    urgency: str
    description: str
    address_type: Literal["yard", "building", "apartment"]
    address_id: int
    media_files: Optional[List[str]] = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        return _validate_request_category(v)

    @field_validator("urgency")
    @classmethod
    def validate_urgency(cls, v: str) -> str:
        # Толерантно (Phase 1): ключ ИЛИ legacy-рус → ключ; иначе ValueError.
        return validate_canonical_urgency(v)


class CreateInspectorRequestBody(BaseModel):
    """Контракт обходчика — building-only (двор/квартира → 422 на уровне схемы)."""

    category: str
    urgency: str
    description: str
    address_type: Literal["building"]
    address_id: int
    media_files: Optional[List[str]] = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        return _validate_request_category(v)

    @field_validator("urgency")
    @classmethod
    def validate_urgency(cls, v: str) -> str:
        return validate_canonical_urgency(v)


class UpdateRequestBody(BaseModel):
    status: Optional[str] = None
    urgency: Optional[str] = None
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

    @field_validator("urgency")
    @classmethod
    def validate_urgency(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return validate_canonical_urgency(v)

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
