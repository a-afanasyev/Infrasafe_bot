"""Pydantic-схемы раздела «Новости и уведомления» (``/api/v2/board-config/notices``)."""
import unicodedata
from datetime import datetime, timezone
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from uk_management_bot.database.models.news_item import NEWS_KINDS
from uk_management_bot.utils.constants import MAX_DESCRIPTION_LENGTH

TITLE_MAX = 200
SCOPE_IDS_MAX = 200
# id справочника — int4: значение вне диапазона Postgres отклонял бы ошибкой (500), а не 422.
DB_ID_MAX = 2_147_483_647
DbId = Annotated[int, Field(ge=1, le=DB_ID_MAX)]

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
    scope_ids: Optional[list[DbId]] = Field(default=None, max_length=SCOPE_IDS_MAX)
    # true — разослать жителям в Telegram (когда запись станет видна); false — отменить ещё не начатую.
    broadcast: Optional[bool] = None

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
    broadcast_attempts: int = 0
    broadcast_next_at: Optional[datetime] = None
    broadcast_details: Optional[dict] = None
    created_by: Optional[int] = None
    closed_by: Optional[int] = None
    closed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    # Кто объявил и кто закрыл — «Имя Фамилия» как в профиле; заполняется в ленте
    # (вкладка «Отключения» показывает, чьё это отключение и кто дал воду).
    created_by_name: Optional[str] = None
    closed_by_name: Optional[str] = None


class NoticesOut(BaseModel):
    items: list[NoticeOut]
    total: int


class AudienceOut(BaseModel):
    """Сколько жителей получит рассылку с такими адресатами."""

    count: int


class OutageIn(BaseModel):
    """Отключение, которое объявляет сантехник на смене."""

    model_config = ConfigDict(extra="forbid")

    resource: Literal["water", "heating"]
    building_ids: list[DbId] = Field(min_length=1, max_length=30)
    duration: Literal["1h", "2h", "4h", "day", "unknown"]


class OutageNoticeOut(BaseModel):
    """Отключение глазами сантехника. Полный ``NoticeOut`` ему не отдаём: в
    ``broadcast_details`` лежат id жителей и чатов домов — это данные менеджера."""

    id: int
    resource: Optional[str] = None
    title_ru: str
    title_uz: str
    status: str
    state: str
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None


class OutageBuildingOut(BaseModel):
    id: int
    address: str


class OutageYardOut(BaseModel):
    id: int
    name: str
    buildings: list[OutageBuildingOut]


class OutageOptionsOut(BaseModel):
    """Экран сантехника: можно ли объявить, справочник домов, идущие отключения."""

    allowed: bool
    # not_plumber | no_active_shift — почему нельзя; null — можно.
    reason: Optional[str] = None
    resources: list[str]
    durations: list[str]
    yards: list[OutageYardOut]
    open: list[OutageNoticeOut]
