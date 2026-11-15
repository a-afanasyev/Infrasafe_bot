"""Контроль менеджера: решения по заданию, замена на день, карточка, табель.

Решение принимается под блокировкой задания и только по той версии, которую
менеджер видел: расхождение ``version`` (например, пришла жалоба) — отказ
``stale``, чтобы решение не перекрыло новое событие вслепую.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.cleaning import (
    CleaningComplaint,
    CleaningDay,
    CleaningPhoto,
    CleaningTask,
    CleaningTaskEvent,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.services.cleaning.assignments import is_cleaner
from uk_management_bot.services.cleaning.public import slot_order
from uk_management_bot.services.cleaning.transitions import TransitionError, log_event, move
from uk_management_bot.utils.business_time import business_today
from uk_management_bot.utils.datetime_utils import as_utc, utc_now

_CLOSED = ("missed", "expired", "rejected")   # принять можно только вручную, с комментарием
_REASSIGNABLE = ("planned", "in_progress")


class ControlError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


async def _lock(db: AsyncSession, task_id: int) -> CleaningTask:
    task = (await db.execute(
        select(CleaningTask).where(CleaningTask.id == task_id).with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if task is None:
        raise ControlError("not_found")
    return task


async def decide(db: AsyncSession, task_id: int, *, to: str, actor_id: int, version: int,
                 comment: Optional[str] = None, now: Optional[datetime] = None) -> CleaningTask:
    """Решение менеджера: принять, отклонить, вернуть на досъёмку или открыть повторно."""
    now = now or utc_now()
    task = await _lock(db, task_id)
    if task.version != version:
        raise ControlError("stale")
    if to == "in_progress":  # досъёмка возможна только пока день задания не кончился
        day = await db.get(CleaningDay, task.work_date)
        if task.work_date != business_today(now) or day is None or now > as_utc(day.day_end_at):
            raise ControlError("day_over")
    reason = (comment or "").strip() or None
    if reason is None and (to == "rejected" or (to == "accepted" and task.status in _CLOSED)):
        raise ControlError("comment_required")
    try:
        await move(db, task, to, kind="decision", actor_id=actor_id, reason=reason)
    except TransitionError:
        raise ControlError("bad_transition") from None
    return task


async def reassign(db: AsyncSession, task_id: int, *, user_id: int, actor_id: int) -> CleaningTask:
    """Срочная замена в день уборки: сменить ответственного у одного задания."""
    task = await _lock(db, task_id)
    if task.status not in _REASSIGNABLE:
        raise ControlError("bad_status")
    if not is_cleaner(await db.get(User, user_id)):
        raise ControlError("not_a_cleaner")
    previous, task.responsible_id = task.responsible_id, user_id
    task.version = (task.version or 1) + 1
    log_event(db, task, "reassigned", actor_id=actor_id, payload={"from": previous, "to": user_id})
    await db.flush()
    return task


@dataclass(frozen=True)
class Card:
    task: CleaningTask
    address: str
    current: list[CleaningPhoto]    # текущие фото точек
    evidence: list[CleaningPhoto]   # поздние и неактивированные — решает менеджер
    other: list[CleaningPhoto]      # заменённые и отказы
    events: list[CleaningTaskEvent]
    complaints: list[CleaningComplaint]


async def card(db: AsyncSession, task_id: int) -> Card:
    task = await db.get(CleaningTask, task_id, populate_existing=True)
    if task is None:
        raise ControlError("not_found")
    building = await db.get(Building, task.building_id)
    photos = sorted((await db.execute(
        select(CleaningPhoto).where(CleaningPhoto.task_id == task_id, CleaningPhoto.state == "done")
        .order_by(CleaningPhoto.id))).scalars().all(), key=lambda photo: slot_order(photo.slot))
    events = (await db.execute(
        select(CleaningTaskEvent).where(CleaningTaskEvent.task_id == task_id)
        .order_by(CleaningTaskEvent.id))).scalars().all()
    complaints = (await db.execute(
        select(CleaningComplaint).where(
            CleaningComplaint.building_id == task.building_id, CleaningComplaint.entrance == task.entrance,
            CleaningComplaint.work_date == task.work_date).order_by(CleaningComplaint.id))).scalars().all()
    return Card(
        task=task, address=building.address if building is not None else "",
        current=[p for p in photos if p.is_current],
        evidence=[p for p in photos if p.outcome == "evidence"],
        other=[p for p in photos if not p.is_current and p.outcome != "evidence"],
        events=list(events), complaints=list(complaints),
    )


@dataclass
class TimesheetRow:
    user_id: int
    planned: int = 0
    accepted: int = 0
    rejected: int = 0
    expired: int = 0
    missed: int = 0
    complaints: int = 0
    confirmed: int = 0

    @property
    def percent(self) -> int:
        return round(self.accepted * 100 / self.planned) if self.planned else 0


async def timesheet(db: AsyncSession, first: date, last: date) -> list[TimesheetRow]:
    """Табель по ответственным за период: задания по статусам и жалобы."""
    rows: dict[int, TimesheetRow] = {}
    tasks = (await db.execute(
        select(CleaningTask.id, CleaningTask.responsible_id, CleaningTask.status)
        .where(CleaningTask.work_date >= first, CleaningTask.work_date <= last,
               CleaningTask.responsible_id.is_not(None)))).all()
    owner: dict[int, int] = {}
    for task_id, user_id, status in tasks:
        owner[task_id] = user_id
        row = rows.setdefault(user_id, TimesheetRow(user_id=user_id))
        row.planned += 1
        if status in ("accepted", "rejected", "expired", "missed"):
            setattr(row, status, getattr(row, status) + 1)
    if owner:
        for task_id, outcome in (await db.execute(
                select(CleaningComplaint.task_id, CleaningComplaint.outcome)
                .where(CleaningComplaint.task_id.in_(owner)))).all():
            row = rows[owner[task_id]]
            row.complaints += 1
            row.confirmed += outcome == "confirmed"
    return sorted(rows.values(), key=lambda r: r.user_id)
