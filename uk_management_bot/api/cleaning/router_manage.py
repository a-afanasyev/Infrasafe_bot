"""API менеджера модуля «Уборка»: ``/api/v2/cleaning``.

План дома (версии с завтра), привязка подъездов к уборщицам, нагрузка по этажам,
настройки. Флаг ``settings.CLEANING_ENABLED`` гейтит весь роутер единым 404.
Всё, что показывает «как будет», считается на завтрашнюю бизнес-дату: правки
плана и привязки начинают действовать с неё.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Response
from sqlalchemy import null, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.cleaning.schemas import (
    DB_ID_MAX,
    CleaningAreasIn,
    CleaningAreasOut,
    CleaningAssignmentIn,
    CleaningBuildingOut,
    CleaningBuildingsOut,
    CleaningStaffMemberOut,
    CleaningEntranceOut,
    CleaningEntranceRef,
    CleaningPlanIn,
    CleaningPlanOut,
    CleaningPlanViewOut,
    CleaningRulesOut,
    CleaningSettingsIn,
    CleaningStaffOut,
)
from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.cleaning import (
    CleaningAssignment,
    CleaningBuildingSettings,
    CleaningPlanVersion,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.services.cleaning import assignments, load, plans, rules
from uk_management_bot.services.cleaning.areas import AreasError, parse_areas
from uk_management_bot.services.cleaning.planning import PlanError
from uk_management_bot.utils.business_time import business_today


async def _require_enabled() -> None:
    if not settings.CLEANING_ENABLED:
        raise HTTPException(status_code=404, detail="Not Found")


router = APIRouter(dependencies=[Depends(_require_enabled)])

_read = require_action("cleaning.read")
_manage = require_action("cleaning.manage")
BuildingId = Path(ge=1, le=DB_ID_MAX)


def _http(code: str) -> HTTPException:
    return HTTPException(status_code=404 if code == "building_not_found" else 422, detail=code)


def _plan_out(version: CleaningPlanVersion | None) -> CleaningPlanOut | None:
    if version is None:
        return None
    return CleaningPlanOut(id=version.id, valid_from=version.valid_from, valid_to=version.valid_to,
                   items=list(version.items), extra_points=list(version.extra_points or []),
                   floor_count=version.floor_count, entrance_count=version.entrance_count)


def _from(day):
    """Действует на дату ``day`` или начнёт действовать позже."""
    return lambda model: or_(model.valid_to.is_(None), model.valid_to >= day)


async def _assigned(db: AsyncSession, day) -> dict[tuple[int, int], int]:
    rows = await db.execute(select(CleaningAssignment).where(
        CleaningAssignment.valid_from <= day, _from(day)(CleaningAssignment)))
    return {(a.building_id, a.entrance): a.user_id for a in rows.scalars()}


# ── дома и план ─────────────────────────────────────────────────────────────

@router.get("/buildings", response_model=CleaningBuildingsOut)
async def list_buildings(db: AsyncSession = Depends(get_db), user: User = Depends(_read)):
    tomorrow = business_today() + timedelta(days=1)
    buildings = (await db.execute(
        select(Building).where(Building.is_active.is_(True)).order_by(Building.address))).scalars().all()
    planned = set((await db.execute(
        select(CleaningPlanVersion.building_id).where(_from(tomorrow)(CleaningPlanVersion)))).scalars())
    shown = {s.building_id: s for s in (await db.execute(select(CleaningBuildingSettings))).scalars()}
    assigned = await _assigned(db, tomorrow)
    return CleaningBuildingsOut(buildings=[
        CleaningBuildingOut(
            id=b.id, address=b.address, yard_id=b.yard_id, floor_count=b.floor_count,
            entrance_count=b.entrance_count, has_plan=b.id in planned,
            show_to_residents=bool(shown[b.id].show_to_residents) if b.id in shown else False,
            show_photos=bool(shown[b.id].show_photos) if b.id in shown else False,
            entrances=[CleaningEntranceOut(entrance=e, user_id=assigned.get((b.id, e)))
                       for e in range(1, b.entrance_count + 1)],
        ) for b in buildings
    ])


@router.get("/buildings/{building_id}/plan", response_model=CleaningPlanViewOut)
async def get_plan(building_id: int = BuildingId, db: AsyncSession = Depends(get_db),
                   user: User = Depends(_read)):
    building = await db.get(Building, building_id)
    if building is None:
        raise _http("building_not_found")
    view = await plans.plan_view(db, building_id)
    return CleaningPlanViewOut(
        building_id=building_id, floor_count=building.floor_count, entrance_count=building.entrance_count,
        current=_plan_out(view.current), upcoming=_plan_out(view.upcoming),
        uncovered=view.uncovered, snapshot_mismatch=view.snapshot_mismatch)


@router.put("/buildings/{building_id}/plan", response_model=CleaningPlanOut)
async def save_plan(body: CleaningPlanIn, building_id: int = BuildingId, db: AsyncSession = Depends(get_db),
                    user: User = Depends(_manage)):
    try:
        version = await plans.save_plan(db, building_id=building_id, items=body.items,
                                        extra_points=body.extra_points, actor_id=user.id)
    except PlanError as exc:
        raise _http(exc.code) from None
    await db.commit()
    return _plan_out(version)


@router.put("/buildings/{building_id}/settings", response_model=CleaningSettingsIn)
async def save_settings(body: CleaningSettingsIn, building_id: int = BuildingId, db: AsyncSession = Depends(get_db),
                        user: User = Depends(_manage)):
    if await db.get(Building, building_id) is None:
        raise _http("building_not_found")
    row = await db.get(CleaningBuildingSettings, building_id)
    if row is None:
        row = CleaningBuildingSettings(building_id=building_id)
        db.add(row)
    row.show_to_residents, row.show_photos = body.show_to_residents, body.show_photos
    await db.commit()
    return body


def _areas_out(building: Building, areas: Any) -> CleaningAreasOut:
    return CleaningAreasOut(building_id=building.id, floor_count=building.floor_count,
                            entrance_count=building.entrance_count, areas=areas)


@router.get("/buildings/{building_id}/areas", response_model=CleaningAreasOut)
async def get_areas(building_id: int = BuildingId, db: AsyncSession = Depends(get_db),
                    user: User = Depends(_read)):
    building = await db.get(Building, building_id)
    if building is None:
        raise _http("building_not_found")
    row = await db.get(CleaningBuildingSettings, building_id)
    return _areas_out(building, row.areas if row is not None else None)


@router.put("/buildings/{building_id}/areas", response_model=CleaningAreasOut)
async def save_areas(body: CleaningAreasIn, building_id: int = BuildingId, db: AsyncSession = Depends(get_db),
                     user: User = Depends(_manage)):
    """Площади мест общего пользования дома; нагрузка в м² сразу считается по ним."""
    building = await db.get(Building, building_id)
    if building is None:
        raise _http("building_not_found")
    try:
        parse_areas(body.areas, floor_count=building.floor_count, entrance_count=building.entrance_count)
    except AreasError as exc:
        raise _http(exc.code) from None
    row = await db.get(CleaningBuildingSettings, building_id)
    if row is None:
        row = CleaningBuildingSettings(building_id=building_id)
        db.add(row)
    # None → SQL NULL, а не JSON null; проверенный JSON канонический (ключи — только «3», «-1»).
    row.areas = body.areas if body.areas is not None else null()
    await db.commit()
    return _areas_out(building, body.areas)


# ── привязка и нагрузка ─────────────────────────────────────────────────────

@router.put("/assignments", status_code=204)
async def put_assignment(body: CleaningAssignmentIn, db: AsyncSession = Depends(get_db),
                         user: User = Depends(_manage)):
    try:
        await assignments.assign(db, building_id=body.building_id, entrances=body.entrances,
                                 user_id=body.user_id, actor_id=user.id)
    except assignments.AssignmentError as exc:
        raise _http(exc.code) from None
    await db.commit()
    return Response(status_code=204)


@router.get("/staff", response_model=CleaningStaffOut)
async def staff(db: AsyncSession = Depends(get_db), user: User = Depends(_read)):
    tomorrow = business_today() + timedelta(days=1)
    current = await rules.latest(db)
    norm, area_norm = int(current["floors_norm_per_day"]), int(current["area_norm_m2_per_day"])
    report = await load.report(db, day=tomorrow, norm=norm, m2_norm=area_norm)
    assigned = await _assigned(db, tomorrow)
    candidates = (await db.execute(
        select(User).where(User.status == "approved",
                           User.specialization.contains(assignments.CLEANING_SPECIALIZATION))
        .order_by(User.first_name, User.id))).scalars().all()
    empty = load.CleanerLoad(norm=norm, m2_norm=area_norm)
    return CleaningStaffOut(
        norm=norm, area_norm=area_norm,
        cleaners=[
            CleaningStaffMemberOut(
                user_id=u.id, first_name=u.first_name, last_name=u.last_name,
                entrances=[CleaningEntranceRef(building_id=b, entrance=e)
                           for (b, e), uid in sorted(assigned.items()) if uid == u.id],
                by_weekday=(entry := report.cleaners.get(u.id, empty)).by_weekday, buildings=entry.buildings,
                week=entry.week, peak=entry.peak, percent=entry.percent, overloaded=entry.overloaded,
                m2_by_weekday=entry.m2_by_weekday, m2_peak=entry.m2_peak, m2_percent=entry.m2_percent,
                missing_areas=sorted(entry.missing_areas),
            ) for u in candidates if assignments.is_cleaner(u)
        ],
        unassigned=[CleaningEntranceRef(building_id=b, entrance=e) for b, e in report.unassigned],
    )


# ── настройки ───────────────────────────────────────────────────────────────

@router.get("/rules", response_model=CleaningRulesOut)
async def get_rules(db: AsyncSession = Depends(get_db), user: User = Depends(_read)):
    current = await rules.latest(db)
    return CleaningRulesOut(version=current.version, data=dict(current.data))


@router.put("/rules", response_model=CleaningRulesOut)
async def put_rules(patch: dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db),
                    user: User = Depends(_manage)):
    """Частичная правка настроек; новая версия действует с завтрашней бизнес-даты."""
    try:
        saved = await rules.save(db, patch, actor_id=user.id)
    except rules.RulesError as exc:
        raise HTTPException(status_code=422, detail=f"bad_rule:{exc.key}") from None
    await db.commit()
    return CleaningRulesOut(version=saved.version, data=dict(saved.data))
