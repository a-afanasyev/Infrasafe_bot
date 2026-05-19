"""Pydantic-схемы конфига публичной витрины resident-board.

`BoardConfigData` — и тело PUT, и payload публичного GET.
"""
from pydantic import BaseModel, field_validator

from uk_management_bot.api.board_config.defaults import MODULE_IDS

_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class LocalizedText(BaseModel):
    ru: str = ""
    uz: str = ""


class OrgCfg(BaseModel):
    name: LocalizedText
    subtitle: LocalizedText


class ContactsCfg(BaseModel):
    dispatch_phone: str = ""
    dispatch_label: LocalizedText
    emergency: LocalizedText


class BotCfg(BaseModel):
    username: str = ""
    label: LocalizedText


class AnnouncementCfg(BaseModel):
    id: str
    icon: str = ""
    important: bool = False
    title: LocalizedText
    text: LocalizedText
    published_at: str = ""


class WorkingHourCfg(BaseModel):
    day: str
    open: str = ""
    close: str = ""
    closed: bool = False

    @field_validator("day")
    @classmethod
    def _known_day(cls, v: str) -> str:
        if v not in _DAYS:
            raise ValueError(f"day must be one of {_DAYS}")
        return v


class LayoutItem(BaseModel):
    id: str
    visible: bool = True

    @field_validator("id")
    @classmethod
    def _known_module(cls, v: str) -> str:
        if v not in MODULE_IDS:
            raise ValueError(f"module id must be one of {MODULE_IDS}")
        return v


class BoardConfigData(BaseModel):
    org: OrgCfg
    contacts: ContactsCfg
    bot: BotCfg
    announcements: list[AnnouncementCfg]
    working_hours: list[WorkingHourCfg]
    layout: list[LayoutItem]

    @field_validator("working_hours")
    @classmethod
    def _seven_unique_days(cls, v: list[WorkingHourCfg]) -> list[WorkingHourCfg]:
        days = [w.day for w in v]
        if set(days) != set(_DAYS):
            raise ValueError("working_hours must cover exactly the 7 days mon..sun")
        return v

    @field_validator("layout")
    @classmethod
    def _all_modules_once(cls, v: list[LayoutItem]) -> list[LayoutItem]:
        ids = [item.id for item in v]
        if set(ids) != set(MODULE_IDS) or len(ids) != len(MODULE_IDS):
            raise ValueError(f"layout must list each module exactly once: {MODULE_IDS}")
        return v
