"""Pydantic-схемы менеджерского API визуальных отчётов «до/после» (T7).

`request_number` ЗДЕСЬ присутствует (в отличие от будущего публичного API,
T8): это аутентифицированный manager-tooling, а не публичная лента — менеджеру
законно нужно сопоставить отчёт с исходной заявкой. Комментарий в модели
(`database/models/work_report.py`: "НИКОГДА не отдаётся наружу") относится
именно к ПУБЛИЧНОМУ API.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from uk_management_bot.api.board_config.schemas import LocalizedText


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
    category_key: Optional[str] = None
    before_media_ids: Optional[list[int]] = None
    after_media_ids: Optional[list[int]] = None
    building_id: Optional[int] = None
    yard_id: Optional[int] = None


class WorkReportRejectIn(BaseModel):
    reason: str


class WorkReportUnpublishIn(BaseModel):
    reason: Optional[str] = None


class WorkReportsSettingsIn(BaseModel):
    autopost: Optional[bool] = None
    limit: Optional[int] = Field(None, ge=1, le=24)
    title: Optional[LocalizedText] = None
