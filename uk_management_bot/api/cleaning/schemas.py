"""Схемы API менеджера модуля «Уборка»."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

DB_ID_MAX = 2_147_483_647


class CleaningPlanIn(BaseModel):
    # Содержимое пунктов проверяет services/cleaning/planning.parse_items (коды PlanError).
    items: list[dict[str, Any]] = Field(max_length=50)
    extra_points: list[str] = Field(default_factory=list, max_length=10)


class CleaningPlanOut(BaseModel):
    id: int
    valid_from: date
    valid_to: Optional[date]
    items: list[dict[str, Any]]
    extra_points: list[str]
    floor_count: int
    entrance_count: int


class CleaningPlanViewOut(BaseModel):
    building_id: int
    floor_count: int
    entrance_count: int
    current: Optional[CleaningPlanOut]
    upcoming: Optional[CleaningPlanOut]
    uncovered: dict[str, list[int]]
    snapshot_mismatch: bool


class CleaningSettingsIn(BaseModel):
    show_to_residents: bool
    show_photos: bool


class CleaningAreasIn(BaseModel):
    # Площади мест общего пользования по подъездам (services/cleaning/areas.py); None — убрать.
    areas: Optional[dict[str, Any]]


class CleaningAreasOut(CleaningAreasIn):
    building_id: int
    floor_count: int
    entrance_count: int


class CleaningEntranceOut(BaseModel):
    entrance: int
    user_id: Optional[int]


class CleaningBuildingOut(BaseModel):
    id: int
    address: str
    yard_id: int
    floor_count: int
    entrance_count: int
    has_plan: bool
    show_to_residents: bool
    show_photos: bool
    entrances: list[CleaningEntranceOut]


class CleaningBuildingsOut(BaseModel):
    buildings: list[CleaningBuildingOut]


class CleaningAssignmentIn(BaseModel):
    building_id: int = Field(ge=1, le=DB_ID_MAX)
    entrances: Optional[list[int]] = Field(default=None, max_length=50)  # None — весь дом
    user_id: Optional[int] = Field(default=None, ge=1, le=DB_ID_MAX)     # None — снять назначение


class CleaningEntranceRef(BaseModel):
    building_id: int
    entrance: int


class CleaningStaffMemberOut(BaseModel):
    user_id: int
    first_name: Optional[str]
    last_name: Optional[str]
    entrances: list[CleaningEntranceRef]
    by_weekday: list[int]
    buildings: dict[int, list[int]]
    week: int
    peak: int
    percent: int
    m2_by_weekday: list[float]
    m2_peak: float
    m2_percent: int
    missing_areas: list[int]  # дома без площадей — их м² в нагрузку не вошли
    overloaded: bool  # по м², если задана норма м², иначе по этажам


class CleaningStaffOut(BaseModel):
    norm: int
    area_norm: int  # 0 — норма м² не задана
    cleaners: list[CleaningStaffMemberOut]
    unassigned: list[CleaningEntranceRef]


class CleaningRulesOut(BaseModel):
    version: Optional[int]
    data: dict[str, Any]
    # До какого момента фото принимаются СЕГОДНЯ. Может отличаться от
    # ``data.day_end_time``: настройки действуют с завтра, кроме продления
    # конца дня. None — сегодняшний день не создан или уже закрыт.
    today_end_at: Optional[datetime] = None
