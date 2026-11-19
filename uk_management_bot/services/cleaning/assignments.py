"""Назначения: кто отвечает за подъезд. История — датами действия.

Один ответственный на подъезд. Правка действует с завтрашней бизнес-даты:
действующее назначение закрывается сегодняшним днём, ещё не начавшееся —
удаляется. Срочная замена в день уборки делается на самом задании, не здесь.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.authz.policy import has_action_roles
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.cleaning import CleaningAssignment
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.business_time import business_today
from uk_management_bot.utils.datetime_utils import utc_now
from uk_management_bot.utils.specializations import parse_specializations

CLEANING_SPECIALIZATION = "cleaning"


class AssignmentError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def is_cleaner(user: Optional[User]) -> bool:
    """Одобренный сотрудник с правом ``cleaning.work`` и специализацией «Уборка»."""
    return (user is not None and user.status == "approved" and getattr(user, "deleted_at", None) is None
            and has_action_roles(user, "cleaning.work")
            and CLEANING_SPECIALIZATION in parse_specializations(user))


async def assign(db: AsyncSession, *, building_id: int, entrances: Optional[list[int]],
                 user_id: Optional[int], actor_id: Optional[int], now: Optional[datetime] = None) -> None:
    """Назначить подъезды дома уборщице с завтра. ``entrances=None`` — весь дом, ``user_id=None`` — снять."""
    building = (await db.execute(
        select(Building).where(Building.id == building_id, Building.is_active.is_(True)).with_for_update()
    )).scalar_one_or_none()
    if building is None:
        raise AssignmentError("building_not_found")
    if entrances is None:
        entrances = list(range(1, building.entrance_count + 1))
    if (not entrances or len(set(entrances)) != len(entrances)
            or any(type(e) is not int or not 1 <= e <= building.entrance_count for e in entrances)):
        raise AssignmentError("bad_entrances")
    if user_id is not None and not is_cleaner(await db.get(User, user_id)):
        raise AssignmentError("not_a_cleaner")

    today = business_today(now or utc_now())
    tomorrow = today + timedelta(days=1)
    active = (await db.execute(
        select(CleaningAssignment).where(
            CleaningAssignment.building_id == building_id, CleaningAssignment.entrance.in_(entrances),
            or_(CleaningAssignment.valid_to.is_(None), CleaningAssignment.valid_to >= tomorrow))
    )).scalars().all()
    keep: set[int] = set()
    for row in active:
        if row.valid_from >= tomorrow:
            await db.delete(row)            # ещё не начало действовать
        elif row.user_id == user_id and row.valid_to is None:
            keep.add(row.entrance)          # уже так и есть — историю не дробим
        else:
            row.valid_to = today
    if user_id is not None:
        db.add_all(CleaningAssignment(building_id=building_id, entrance=e, user_id=user_id,
                                      valid_from=tomorrow, created_by=actor_id)
                   for e in entrances if e not in keep)
    db.add(AuditLog(user_id=actor_id, action="cleaning.assign", details={
        "building_id": building_id, "entrances": entrances, "user_id": user_id,
        "valid_from": tomorrow.isoformat()}))
    await db.flush()
