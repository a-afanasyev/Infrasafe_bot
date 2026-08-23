"""Pydantic-схемы реестра мониторимых ТГ-групп (Group Intake)."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, field_validator

from uk_management_bot.database.models.monitored_group import GROUP_KINDS


class MonitoredGroupCreate(BaseModel):
    chat_id: int
    title: Optional[str] = None
    kind: str = "residents"
    # Тег-режим: обрабатывать только сообщения с #заявка/#ariza.
    require_tag: bool = False

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: str) -> str:
        if v not in GROUP_KINDS:
            raise ValueError(f"kind must be one of {GROUP_KINDS}")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()[:255] or None
        return v


class MonitoredGroupUpdate(BaseModel):
    is_active: Optional[bool] = None
    title: Optional[str] = None
    kind: Optional[str] = None
    require_tag: Optional[bool] = None

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in GROUP_KINDS:
            raise ValueError(f"kind must be one of {GROUP_KINDS}")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()[:255] or None
        return v


class MonitoredGroupOut(BaseModel):
    id: int
    chat_id: int
    title: Optional[str] = None
    kind: str
    is_active: bool
    require_tag: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MonitoredGroupListOut(BaseModel):
    items: List[MonitoredGroupOut]
    total: int
