"""Жалоба жителя на уборку подъезда.

Критичная часть — один шаг в одной транзакции под блокировкой задания: строка
жалобы, перевод принятого задания на проверку и событие. Заявка категории
``cleaning`` создаётся вторым шагом (API/тик) и только дописывает номер:
перевод на проверку не зависит от того, создалась ли заявка.

Жалоба на ещё не завершённое задание статус не меняет — её увидит правило
автоприёмки при закрытии последнего слота (``acceptance.evaluate``).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.cleaning import CleaningComplaint, CleaningTask
from uk_management_bot.services.cleaning.transitions import log_event, move
from uk_management_bot.utils.datetime_utils import utc_now

DECISIONS = ("confirmed", "unfounded")
DAILY_LIMIT = 3  # жалоб одного жителя в день: иначе один человек отправит на проверку весь дом


class ComplaintLimit(Exception):
    """Житель исчерпал жалобы на сегодня."""


def _same(author_id: int, building_id: int, entrance: int, work_date: date):
    return (CleaningComplaint.author_id == author_id, CleaningComplaint.building_id == building_id,
            CleaningComplaint.entrance == entrance, CleaningComplaint.work_date == work_date)


async def file_complaint(db: AsyncSession, *, author_id: int, building_id: int, entrance: int,
                         work_date: date) -> CleaningComplaint:
    """Записать жалобу и, если задание принято, отправить его на проверку. Повтор безопасен."""
    mine = list((await db.execute(
        select(CleaningComplaint).where(CleaningComplaint.author_id == author_id,
                                        CleaningComplaint.work_date == work_date)
    )).scalars())
    for existing in mine:
        if (existing.building_id, existing.entrance) == (building_id, entrance):
            return existing
    if len(mine) >= DAILY_LIMIT:
        raise ComplaintLimit

    task: Optional[CleaningTask] = (await db.execute(
        select(CleaningTask).where(CleaningTask.building_id == building_id, CleaningTask.entrance == entrance,
                                   CleaningTask.work_date == work_date).with_for_update()
    )).scalar_one_or_none()
    complaint = CleaningComplaint(author_id=author_id, building_id=building_id, entrance=entrance,
                                  work_date=work_date, task_id=task.id if task is not None else None)
    try:
        async with db.begin_nested():
            db.add(complaint)
            await db.flush()
    except IntegrityError:  # эта жалоба уже есть — одна на жителя, подъезд и день
        return (await db.execute(
            select(CleaningComplaint).where(*_same(author_id, building_id, entrance, work_date))
        )).scalar_one()

    if task is not None:
        payload = {"complaint_id": complaint.id}
        if task.status == "accepted":
            await move(db, task, "review", kind="complaint", actor_id=author_id, payload=payload)
        else:
            log_event(db, task, "complaint_recorded", actor_id=author_id, payload=payload)
            task.version += 1  # решение менеджера по карточке без этой жалобы получит stale
            await db.flush()
    return complaint


async def without_request(db: AsyncSession) -> list[CleaningComplaint]:
    """Жалобы, по которым заявка ещё не создана (досоздаёт тик)."""
    return list((await db.execute(
        select(CleaningComplaint).where(CleaningComplaint.request_number.is_(None))
        .order_by(CleaningComplaint.id)
    )).scalars())


async def attach_request(db: AsyncSession, complaint_id: int, request_number: str) -> None:
    complaint = await db.get(CleaningComplaint, complaint_id)
    if complaint is not None and complaint.request_number is None:
        complaint.request_number = request_number
        await db.flush()


async def decide(db: AsyncSession, complaint_id: int, *, outcome: str, actor_id: int,
                 now: Optional[datetime] = None) -> Optional[CleaningComplaint]:
    """Итог разбора жалобы: подтвердилась или нет. None — жалобы нет."""
    if outcome not in DECISIONS:
        raise ValueError(outcome)
    complaint = await db.get(CleaningComplaint, complaint_id)
    if complaint is not None:
        complaint.outcome, complaint.decided_by, complaint.decided_at = outcome, actor_id, now or utc_now()
        await db.flush()
    return complaint
