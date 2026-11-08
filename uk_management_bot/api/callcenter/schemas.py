from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal, Optional

from uk_management_bot.api.requests.schemas import (
    _AddressLevelMixin,
    _ElevatorFieldsMixin,
    _validate_request_category,
)
from uk_management_bot.utils.constants import (
    ACCEPTANCE_MODES,
    MAX_DESCRIPTION_LENGTH,
    validate_canonical_urgency,
)


class ResidentSearchResult(BaseModel):
    id: int
    telegram_id: int
    full_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    requests_count: int = 0

    model_config = {"from_attributes": True}


class CallCenterCreateRequest(_AddressLevelMixin, _ElevatorFieldsMixin):
    """Заявка колл-центра. Адрес — ровно один уровень из справочника
    (решение владельца 2026-11-07: заявки без адреса из справочника не
    принимаются; свободный текст адреса больше не принимается):

    * ``apartment_id`` — квартира; с ``user_id`` — обязана быть квартирой этого
      жителя, без ``user_id`` — любая активная (владелец — менеджер-актор);
    * ``building_id`` — дом (любой активный);
    * ``yard_id`` — двор (любой активный).

    Лифт (``elevator_id``/``elevator_operational``) — ``_ElevatorFieldsMixin``:
    обязателен для категории «лифт» при включённом флаге.
    """

    category: str
    urgency: str
    # A10-API-06: те же потолки, что у заявки жителя (`requests/schemas.py`):
    # текст уходит в Telegram-уведомления (4096) и карточки.
    description: str = Field(max_length=MAX_DESCRIPTION_LENGTH)
    user_id: Optional[int] = None
    caller_name: Optional[str] = Field(default=None, max_length=200)
    caller_phone: Optional[str] = Field(default=None, max_length=32)
    # Адрес со слов звонящего (подсказка ИИ, 2026-11-07) — не адрес заявки, а
    # детали для исполнителя («10 этаж»): уходит в примечания.
    address_text: Optional[str] = Field(default=None, max_length=300)
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


class CallCenterCapabilities(BaseModel):
    """Что доступно форме колл-центра на этой площадке."""

    # Свободный ввод адреса с подсказкой ИИ — при включённом ИИ-менеджере.
    address_suggest: bool


class AddressSuggestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address_text: str = Field(min_length=2, max_length=300)
    # Описание проблемы — контекст для ИИ (как сообщение в группе).
    description: Optional[str] = Field(default=None, max_length=2000)


class AddressOption(BaseModel):
    type: Literal["yard", "building"]
    id: int
    yard_id: int
    label: str


class AddressSuggestOut(BaseModel):
    """Варианты адреса из справочника; выбирает человек."""

    options: list[AddressOption]
    ai_used: bool
    category: Optional[str] = None
    urgency: Optional[str] = None
