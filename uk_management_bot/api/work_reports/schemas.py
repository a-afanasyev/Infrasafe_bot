"""Pydantic-схемы менеджерского API визуальных отчётов «до/после» (T7).

`request_number` ЗДЕСЬ присутствует (в отличие от будущего публичного API,
T8): это аутентифицированный manager-tooling, а не публичная лента — менеджеру
законно нужно сопоставить отчёт с исходной заявкой. Комментарий в модели
(`database/models/work_report.py`: "НИКОГДА не отдаётся наружу") относится
именно к ПУБЛИЧНОМУ API.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from uk_management_bot.api.board_config.schemas import LocalizedText
from uk_management_bot.services.work_report_service import MAX_MEDIA_PER_SIDE


class WorkReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    request_number: str
    category_key: str
    address_public: str
    performed_at: datetime
    before_media_ids: list[int]
    after_media_ids: list[int]
    media_meta: list[dict]
    locked_media_ids: list[int]
    status: str
    source: str
    reject_reason: Optional[str] = None
    created_at: datetime
    published_at: Optional[datetime] = None
    media_synced_at: Optional[datetime] = None
    state_changed_at: Optional[datetime] = None
    moderated_by: Optional[int] = None


class WorkReportListOut(BaseModel):
    items: list[WorkReportOut]
    total: int
    limit: int
    offset: int


class WorkReportCreateIn(BaseModel):
    request_number: str
    building_id: Optional[int] = None
    yard_id: Optional[int] = None


class WorkReportPatchIn(BaseModel):
    # extra="forbid" именно здесь: у PATCH'а нет поля свободного адреса (адрес
    # выводится из связей заявки, override — только building_id/yard_id для
    # legacy), и клиент, приславший `address_public`, по умолчанию получал 200 с
    # молча выброшенным полем — то есть «адрес изменён» с точки зрения вызывающего,
    # хотя ничего не изменилось. Для ручки, правящей содержимое публичной
    # карточки, тихое игнорирование опечатки — плохой контракт.
    model_config = ConfigDict(extra="forbid")

    category_key: Optional[str] = None
    # Тот же cap, что применяет autofill_media — иначе ручной PATCH обходил бы
    # его и морозил произвольно длинный список (столько же publication-lock'ов
    # на публикации, и лишние id, которые карточка всё равно не показывает).
    before_media_ids: Optional[list[int]] = Field(None, max_length=MAX_MEDIA_PER_SIDE)
    after_media_ids: Optional[list[int]] = Field(None, max_length=MAX_MEDIA_PER_SIDE)
    building_id: Optional[int] = None
    yard_id: Optional[int] = None

    @field_validator("category_key")
    @classmethod
    def _known_category(cls, v: Optional[str]) -> Optional[str]:
        """`category_key` уходит в публичную ленту, поэтому валидируем на границе,
        а не доверяем клиенту: неизвестный ключ фронт отрендерил бы как сырую
        строку (`i18n/apiMaps.ts:tCategory` при промахе логирует warn и печатает
        ключ). Импорт ленивый — `keyboards.requests` тянет aiogram.types (тот же
        приём в work_report_service.sync_pending_drafts и api/requests/schemas.py).
        """
        if v is None:
            return v
        from uk_management_bot.keyboards.requests import CANONICAL_CATEGORY_KEYS

        if v not in CANONICAL_CATEGORY_KEYS:
            raise ValueError(f"category_key must be one of {sorted(CANONICAL_CATEGORY_KEYS)}")
        return v


class WorkReportRejectIn(BaseModel):
    reason: str


class WorkReportUnpublishIn(BaseModel):
    reason: Optional[str] = None


class WorkReportsSettingsIn(BaseModel):
    autopost: Optional[bool] = None
    # Публикация без модерации. Валидацию значения не дублируем — bool.
    autopublish: Optional[bool] = None
    # Фильтр категорий. Проверку на канонические ключи делает
    # `WorkReportsCfg._known_categories` при сборке итогового конфига в
    # merge_and_save_board_config — здесь достаточно типа, иначе один и тот же
    # список ключей валидировался бы в двух местах.
    categories: Optional[list[str]] = None
    limit: Optional[int] = Field(None, ge=1, le=24)
    title: Optional[LocalizedText] = None
