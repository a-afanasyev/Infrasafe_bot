"""Что видят жители: «уборка сегодня» по домам и дом по подъездам.

Наружу уходит только статус и расписание — без имён сотрудников, причин
проверки и деталей контроля. Житель видит «убрано» лишь у принятого задания:
на проверке, отклонённое и незавершённое для него одинаково «ещё не убрано».
Фото — только точки из публичного набора и только при включённом показе.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.cleaning import (
    CleaningBuildingSettings,
    CleaningPhoto,
    CleaningPlanVersion,
    CleaningTask,
)
from uk_management_bot.services.cleaning.planning import FIRST_FLOOR_POINTS, WEEKDAYS, PlanError, parse_items
from uk_management_bot.utils.business_time import business_today

# Жителю в приложении — коротко: одно фото подъезда и лифт, если его мыли.
# Все фото принятого задания — на странице-обзоре (решение владельца 2026-11-16).
BRIEF_POINTS = ("point:elevator",)
_STARTED = ("in_progress", "review", "accepted", "rejected", "expired")


@dataclass(frozen=True)
class EntranceToday:
    entrance: int
    state: str  # done / pending / none
    done_at: Optional[datetime]
    photo_ids: list[int]


@dataclass(frozen=True)
class BuildingToday:
    building_id: int
    address: str
    state: str  # done / in_progress / planned / none
    done_at: Optional[datetime]  # когда принят последний подъезд; только у убранного дома
    entrances: list[EntranceToday]


@dataclass(frozen=True)
class BuildingView:
    building_id: int
    address: str
    entrance_count: int
    entrances: list[EntranceToday]
    week: list[list[dict]]  # пн…вс: работы дня с отрезком этажей


def _state(statuses: list[str]) -> str:
    if not statuses:
        return "none"
    if all(s == "accepted" for s in statuses):
        return "done"
    return "in_progress" if any(s in _STARTED for s in statuses) else "planned"


async def _shown(db: AsyncSession) -> dict[int, tuple[Building, CleaningBuildingSettings]]:
    rows = await db.execute(
        select(Building, CleaningBuildingSettings)
        .join(CleaningBuildingSettings, CleaningBuildingSettings.building_id == Building.id)
        .where(Building.is_active.is_(True), CleaningBuildingSettings.show_to_residents.is_(True))
        .order_by(Building.address))
    return {building.id: (building, cfg) for building, cfg in rows.all()}


def _slot_order(slot: str) -> tuple[int, int, str]:
    """Точки первого этажа, этажи по номеру (10-й после 9-го), затем прочие точки по имени."""
    if slot in FIRST_FLOOR_POINTS:
        return (0, FIRST_FLOOR_POINTS.index(slot), "")
    kind, _, name = slot.partition(":")
    return (1, int(name), "") if kind == "floor" and name.isdigit() else (2, 0, name)


async def _photo_ids(db: AsyncSession, task_ids: list[int], *, brief: bool = False) -> dict[int, list[int]]:
    """Текущие фото заданий: задание → id фото по порядку точек.

    ``brief`` — выжимка для жителя: одно фото подъезда (первая точка первого этажа
    либо нижний снятый этаж) и лифт.
    """
    shots: dict[int, list[tuple[str, int]]] = {}
    if task_ids:
        for task_id, slot, photo_id in (await db.execute(
                select(CleaningPhoto.task_id, CleaningPhoto.slot, CleaningPhoto.id)
                .where(CleaningPhoto.task_id.in_(task_ids), CleaningPhoto.is_current.is_(True),
                       CleaningPhoto.media_id.is_not(None)))).all():
            shots.setdefault(task_id, []).append((slot, photo_id))
    photos = {}
    for task_id, rows in shots.items():
        rows.sort(key=lambda row: _slot_order(row[0]))
        if brief:
            floors = [row for row in rows if row[0].startswith("floor:") or row[0] in FIRST_FLOOR_POINTS]
            rows = floors[:1] + [row for row in rows if row[0] in BRIEF_POINTS]
        photos[task_id] = [photo_id for _, photo_id in rows]
    return photos


def _entrances(building: Building, tasks: dict[int, CleaningTask],
               photos: dict[int, list[int]]) -> list[EntranceToday]:
    """Подъезды дома: «убрано» и фото — только у принятого задания."""
    entrances = []
    for number in range(1, building.entrance_count + 1):
        task = tasks.get(number)
        done = task is not None and task.status == "accepted"
        entrances.append(EntranceToday(
            entrance=number, state="none" if task is None else "done" if done else "pending",
            done_at=task.updated_at if done else None, photo_ids=photos.get(task.id, []) if done else []))
    return entrances


async def today(db: AsyncSession, day: date) -> list[BuildingToday]:
    """Все дома, показанные жителям: состояние дня, подъезды и фото (где показ фото включён)."""
    shown = await _shown(db)
    if not shown:
        return []
    by_building: dict[int, dict[int, CleaningTask]] = {}
    for task in (await db.execute(
            select(CleaningTask).where(CleaningTask.work_date == day, CleaningTask.building_id.in_(shown)))).scalars():
        by_building.setdefault(task.building_id, {})[task.entrance] = task
    photos = await _photo_ids(db, [
        task.id for bid, tasks in by_building.items() if shown[bid][1].show_photos
        for task in tasks.values() if task.status == "accepted"])
    rows = []
    for bid, (building, _) in shown.items():
        tasks = by_building.get(bid, {})
        state = _state([task.status for task in tasks.values()])
        entrances = _entrances(building, tasks, photos)
        rows.append(BuildingToday(
            building_id=bid, address=building.address, state=state, entrances=entrances,
            done_at=max((e.done_at for e in entrances if e.done_at), default=None) if state == "done" else None))
    return rows


async def building_view(db: AsyncSession, building_id: int, day: date) -> Optional[BuildingView]:
    found = (await _shown(db)).get(building_id)
    if found is None:
        return None
    building, cfg = found
    tasks = {t.entrance: t for t in (await db.execute(
        select(CleaningTask).where(CleaningTask.building_id == building_id, CleaningTask.work_date == day))).scalars()}
    accepted = [t.id for t in tasks.values() if t.status == "accepted"]
    photos = await _photo_ids(db, accepted if cfg.show_photos else [], brief=True)
    return BuildingView(building_id=building_id, address=building.address,
                        entrance_count=building.entrance_count, entrances=_entrances(building, tasks, photos),
                        week=await _week(db, building_id, day))


async def _week(db: AsyncSession, building_id: int, day: date) -> list[list[dict]]:
    version = (await db.execute(
        select(CleaningPlanVersion).where(
            CleaningPlanVersion.building_id == building_id, CleaningPlanVersion.valid_from <= day,
            or_(CleaningPlanVersion.valid_to.is_(None), CleaningPlanVersion.valid_to >= day))
    )).scalar_one_or_none()
    if version is None:
        return [[] for _ in WEEKDAYS]
    try:
        items = parse_items(version.items, floor_count=version.floor_count, entrance_count=version.entrance_count)
    except PlanError:
        return [[] for _ in WEEKDAYS]
    week = []
    for weekday in WEEKDAYS:
        works = []
        for item in items:
            if weekday in item.weekdays:
                work = {"work_kind": item.work_kind}
                if item.floors:
                    work.update(floor_from=item.floors[0], floor_to=item.floors[-1])
                works.append(work)
        week.append(works)
    return week


async def public_photo(db: AsyncSession, photo_id: int) -> Optional[CleaningPhoto]:
    """Фото, которое сейчас можно отдать жителям; иначе None."""
    photo = await db.get(CleaningPhoto, photo_id)
    if photo is None or not photo.is_current or photo.media_id is None:
        return None
    task = await db.get(CleaningTask, photo.task_id, populate_existing=True)
    cfg = await db.get(CleaningBuildingSettings, task.building_id, populate_existing=True) if task else None
    # Только сегодняшние: перебором id не достать архив фото подъездов за прошлые дни.
    if task is None or task.status != "accepted" or cfg is None or task.work_date != business_today():
        return None
    return photo if cfg.show_to_residents and cfg.show_photos else None
