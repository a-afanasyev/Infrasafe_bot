"""Автоприёмка завершённого задания: список причин, по которым нужен человек.

Вызывается в финализации последнего слота, под блокировкой задания. Решают
правила; причин нет и выборка не выпала — задание принимается само. Отклонить
задание автоматически нельзя: любая причина только отправляет его на проверку.

Правила — по серверным фактам: уровень доверия, повтор и сходство кадров,
скорость, жалоба, испытательный срок. ИИ-проверка добавится сюда же отдельной
причиной (этап 6).
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.cleaning import CleaningComplaint, CleaningPhoto, CleaningTask
from uk_management_bot.services.cleaning.rules import Rules
from uk_management_bot.utils.datetime_utils import as_utc

_DECIDED = ("accepted", "review", "rejected")


@dataclass(frozen=True)
class Verdict:
    reasons: tuple[str, ...]
    sampled: bool

    @property
    def accept(self) -> bool:
        return not self.reasons and not self.sampled


def pick_sampled(rules: Rules) -> bool:
    """Выборочный контроль: 1 из N, решается один раз под блокировкой задания."""
    every = int(rules["sample_every"])
    return every > 0 and secrets.randbelow(every) == 0


async def on_probation(db: AsyncSession, user_id: Optional[int], day: date, rules: Rules) -> bool:
    """Первые ``probation_days`` от первого завершённого задания уборщицы."""
    if user_id is None:
        return False
    first = (await db.execute(
        select(func.min(CleaningTask.work_date))
        .where(CleaningTask.responsible_id == user_id, CleaningTask.status.in_(_DECIDED))
    )).scalar_one_or_none()
    return first is None or day - first < timedelta(days=int(rules["probation_days"]))


async def evaluate(db: AsyncSession, task: CleaningTask, rules: Rules) -> Verdict:
    photos = (await db.execute(
        select(CleaningPhoto).where(CleaningPhoto.task_id == task.id, CleaningPhoto.is_current.is_(True))
    )).scalars().all()
    trusted = {"live", "deferred"} if rules["allow_deferred_auto"] else {"live"}
    reasons: list[str] = []

    if any(p.trust_level not in trusted for p in photos):
        reasons.append("not_live")

    hashes = [p.pixel_sha256 for p in photos if p.pixel_sha256]
    repeated = len(set(hashes)) < len(hashes) or (hashes and (await db.execute(
        select(CleaningPhoto.id).where(CleaningPhoto.pixel_sha256.in_(hashes),
                                       CleaningPhoto.task_id != task.id).limit(1)
    )).first() is not None)
    if repeated:
        reasons.append("duplicate_photo")

    complaint = (await db.execute(
        select(CleaningComplaint.id).where(
            CleaningComplaint.building_id == task.building_id, CleaningComplaint.entrance == task.entrance,
            CleaningComplaint.work_date == task.work_date).limit(1)
    )).first()
    if complaint is not None:
        reasons.append("complaint")

    if await _similar_to_earlier(db, task, photos, rules):
        reasons.append("similar_photo")

    if _too_fast([as_utc(p.received_at) for p in photos], int(rules["min_seconds_per_floor"])):
        reasons.append("too_fast")

    if await on_probation(db, task.responsible_id, task.work_date, rules):
        reasons.append("probation")

    return Verdict(reasons=tuple(reasons), sampled=not reasons and pick_sampled(rules))


def _too_fast(received: list[datetime], min_seconds: int) -> bool:
    """Все точки сняты быстрее, чем можно пройти подъезд."""
    if min_seconds <= 0 or len(received) < 2:
        return False
    return (max(received) - min(received)).total_seconds() < (len(received) - 1) * min_seconds


async def _similar_to_earlier(db: AsyncSession, task: CleaningTask, photos: list[CleaningPhoto],
                              rules: Rules) -> bool:
    """Кадр почти совпадает с прошлым фото ТОЙ ЖЕ точки этого подъезда.

    Одинаково чистый коридор похож сам на себя, поэтому порог строгий (несколько
    бит из 64) и это только повод показать человеку, не отказ.
    """
    window, distance = int(rules["similar_days"]), int(rules["similar_distance"])
    mine = {p.slot: int(p.dhash, 16) for p in photos if p.dhash}
    if window <= 0 or not mine:
        return False
    earlier = await db.execute(
        select(CleaningPhoto.slot, CleaningPhoto.dhash)
        .join(CleaningTask, CleaningTask.id == CleaningPhoto.task_id)
        .where(CleaningTask.building_id == task.building_id, CleaningTask.entrance == task.entrance,
               CleaningTask.id != task.id, CleaningTask.work_date >= task.work_date - timedelta(days=window),
               CleaningPhoto.slot.in_(mine), CleaningPhoto.outcome == "activated",
               CleaningPhoto.dhash.is_not(None)))
    return any((mine[slot] ^ int(dhash, 16)).bit_count() <= distance for slot, dhash in earlier.all())
