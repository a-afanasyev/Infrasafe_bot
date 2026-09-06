from pydantic import BaseModel, field_validator, model_validator
from typing import Optional

from uk_management_bot.api.requests.schemas import (
    _ElevatorFieldsMixin,
    _validate_request_category,
)
from uk_management_bot.utils.constants import ACCEPTANCE_MODES, validate_canonical_urgency


class ResidentSearchResult(BaseModel):
    id: int
    telegram_id: int
    full_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    requests_count: int = 0

    model_config = {"from_attributes": True}


class CallCenterCreateRequest(_ElevatorFieldsMixin):
    """Заявка колл-центра. Адрес — один из трёх вариантов:

    * ``user_id`` + ``apartment_id`` — квартира жителя (дом = дом квартиры);
    * ``building_id`` — уровень дома (ремонт лифта из карточки, T5/T6): любой
      активный дом, владелец — менеджер-актор, если ``user_id`` не задан;
    * иначе свободный ``address`` (legacy) — лифт к такой заявке не привязать.

    Лифт (``elevator_id``/``elevator_operational``) — ``_ElevatorFieldsMixin``:
    обязателен для категории «лифт» при включённом флаге.
    """

    category: str
    urgency: str
    description: str
    user_id: Optional[int] = None
    apartment_id: Optional[int] = None
    building_id: Optional[int] = None
    caller_name: Optional[str] = None
    caller_phone: Optional[str] = None
    address: Optional[str] = None
    # Кто принимает результат (Р3/Р9 — ремонт лифта из карточки: приёмка
    # менеджером). None → дефолт модели ('resident', как и раньше). Канон —
    # ACCEPTANCE_MODES (CHECK ck_requests_acceptance_mode).
    acceptance_mode: Optional[str] = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        # Та же валидация, что у applicant/inspector — менеджер не должен заводить
        # заявку с произвольной категорией (полонит Kanban/аналитику/webhook).
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
    def _one_address_level(self):
        # Ровно один FK у заявки (CHECK ck_requests_address_type_fk).
        if self.building_id is not None and self.apartment_id is not None:
            raise ValueError("building_id and apartment_id are mutually exclusive")
        return self
