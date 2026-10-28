"""Pydantic-схемы мониторинга отключений (dashboard + inbox юзербота).

Бизнес-валидация конфига — в ``services/news_watch/config.validate_config``
(единый источник правил для API и воркера); здесь только типы и мост.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from uk_management_bot.services.news_watch.config import DEFAULT_CONFIG, validate_config


class NewsSource(BaseModel):
    chat: str
    title: str = ""


class NewsWatchConfigData(BaseModel):
    sources: list[NewsSource] = Field(default_factory=list)
    complex_context: str = ""
    keywords: list[str] = Field(default_factory=lambda: list(DEFAULT_CONFIG["keywords"]))
    auto_publish: bool = False
    min_confidence: float = DEFAULT_CONFIG["min_confidence"]
    broadcast: dict = Field(default_factory=lambda: dict(DEFAULT_CONFIG["broadcast"]))

    @model_validator(mode="after")
    def _validate_via_shared_rules(self) -> "NewsWatchConfigData":
        validate_config(self.model_dump())
        return self


class NewsItemOut(BaseModel):
    id: int
    source_chat_id: int
    source_message_id: int
    chat_title: Optional[str] = None
    raw_text: str
    posted_at: Optional[datetime] = None
    kind: Optional[str] = None
    relevant: Optional[bool] = None
    confidence: Optional[float] = None
    summary_ru: Optional[str] = None
    summary_uz: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    status: str
    published_at: Optional[datetime] = None
    decided_by: Optional[int] = None
    broadcast_status: str
    broadcast_attempts: int
    broadcast_details: Optional[dict] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class NewsItemsOut(BaseModel):
    items: list[NewsItemOut]
    total: int


class InboxIn(BaseModel):
    """Сырое сообщение от юзербота (service-token)."""
    source_chat_id: int
    source_message_id: int
    chat_title: Optional[str] = Field(default=None, max_length=255)
    text: str = Field(min_length=1, max_length=20000)
    posted_at: Optional[datetime] = None


class InboxOut(BaseModel):
    id: int
    status: str
    created: bool


class SourcesOut(BaseModel):
    sources: list[NewsSource]
