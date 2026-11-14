"""Pydantic-схемы раздела «Новости и уведомления» (``/api/v2/notices``)."""
import unicodedata
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from uk_management_bot.database.models.news_item import NEWS_KINDS
from uk_management_bot.utils.constants import MAX_DESCRIPTION_LENGTH

TITLE_MAX = 200
SCOPE_IDS_MAX = 200

NoticeKind = Literal["news", "outage"]
NoticeScope = Literal["all", "yards", "buildings"]


class NoticeIn(BaseModel):
    """Создание и правка записи. Запрос без поля оставляет его прежним (PATCH)."""

    model_config = ConfigDict(extra="forbid")

    kind: Optional[NoticeKind] = None
    resource: Optional[str] = None
    title_ru: Optional[str] = Field(default=None, max_length=TITLE_MAX)
    title_uz: Optional[str] = Field(default=None, max_length=TITLE_MAX)
    text_ru: Optional[str] = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    text_uz: Optional[str] = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    place_ru: Optional[str] = Field(default=None, max_length=TITLE_MAX)
    place_uz: Optional[str] = Field(default=None, max_length=TITLE_MAX)
    icon: Optional[str] = Field(default=None, max_length=16)
    important: Optional[bool] = None
    publish_at: Optional[datetime] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    all_day: Optional[bool] = None
    expires_at: Optional[datetime] = None
    scope: Optional[NoticeScope] = None
    scope_ids: Optional[list[int]] = Field(default=None, max_length=SCOPE_IDS_MAX)

    @field_validator("title_ru", "title_uz", "text_ru", "text_uz", "place_ru", "place_uz", "icon")
    @classmethod
    def _printable(cls, value: Optional[str], info) -> Optional[str]:
        """Текст уходит на публичные страницы и (этап 2) в Telegram: управляющие
        символы и невидимые метки направления письма не принимаем. NUL к тому
        же отклоняет Postgres — без проверки это был бы 500, а не 422."""
        if value is None:
            return value
        multiline = info.field_name.startswith("text_")
        for ch in value:
            category = unicodedata.category(ch)
            if category == "Cc" and not (multiline and ch in "\n\r\t"):
                raise ValueError("control characters are not allowed")
            # Cf: zero-width joiner и variation selector нужны составным эмодзи.
            if category == "Cf" and ch not in "\u200d\ufe0f":
                raise ValueError("invisible formatting characters are not allowed")
        return value

    @model_validator(mode="after")
    def _consistent(self) -> "NoticeIn":
        if self.resource is not None and self.resource not in NEWS_KINDS:
            raise ValueError(f"resource must be one of {NEWS_KINDS}")
        for name in ("publish_at", "starts_at", "ends_at", "expires_at"):
            value = getattr(self, name)
            if value is None:
                continue
            if value.tzinfo is None:
                raise ValueError(f"{name} must include a timezone offset")
            # Храним UTC: sqlite в тестах отбрасывает смещение, не пересчитывая.
            try:
                setattr(self, name, value.astimezone(timezone.utc))
            except OverflowError as e:  # год 1 или 9999 со смещением
                raise ValueError(f"{name} is out of range") from e
        if self.starts_at and self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("ends_at must not be earlier than starts_at")
        return self


class NoticeCreateIn(NoticeIn):
    kind: NoticeKind
    title_ru: str = Field(min_length=1, max_length=TITLE_MAX)
    # true — опубликовать сразу (или к publish_at); false — черновик.
    publish: bool = False

    @model_validator(mode="after")
    def _outage_window(self) -> "NoticeCreateIn":
        if self.kind == "outage":
            if self.resource is None:
                raise ValueError("resource is required for an outage")
            if self.starts_at is None:
                raise ValueError("starts_at is required for an outage")
        return self


class NoticeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    resource: Optional[str] = None
    source: str
    news_item_id: Optional[int] = None
    title_ru: str
    title_uz: str
    text_ru: str
    text_uz: str
    place_ru: str
    place_uz: str
    icon: str
    important: bool
    status: str
    # draft | scheduled | active | expired | closed — производное от статуса и времени.
    state: str
    publish_at: Optional[datetime] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    all_day: bool
    expires_at: Optional[datetime] = None
    scope: str
    scope_ids: list[int]
    broadcast_status: str
    created_by: Optional[int] = None
    closed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class NoticesOut(BaseModel):
    items: list[NoticeOut]
    total: int
