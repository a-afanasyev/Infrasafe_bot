"""API контроля уборки для менеджера: ``/api/v2/cleaning/control``.

Матрица план/факт, карточка задания с фото и журналом, решение по заданию,
замена ответственного на день, жалобы, табель. Гейт — ``CLEANING_ENABLED``.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.cleaning import (
    CleaningComplaint,
    CleaningPhoto,
    CleaningTask,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.services.cleaning import complaints, control
from uk_management_bot.utils.business_time import business_today

DB_ID_MAX = 2_147_483_647
MAX_RANGE_DAYS = 62


async def _require_enabled() -> None:
    if not settings.CLEANING_ENABLED:
        raise HTTPException(status_code=404, detail="Not Found")


router = APIRouter(dependencies=[Depends(_require_enabled)])
_read = require_action("cleaning.read")
_manage = require_action("cleaning.manage")
TaskId = Path(ge=1, le=DB_ID_MAX)

_ERROR_STATUS = {"not_found": 404, "stale": 409, "bad_transition": 409, "bad_status": 409, "day_over": 409}


def _http(exc: control.ControlError) -> HTTPException:
    return HTTPException(status_code=_ERROR_STATUS.get(exc.code, 422), detail=exc.code)


class CleaningTaskRowOut(BaseModel):
    id: int
    building_id: int
    address: str
    entrance: int
    work_date: date
    status: str
    responsible_id: Optional[int]
    slots_total: int
    slots_done: int
    sampled: Optional[bool]


class CleaningTasksOut(BaseModel):
    date_from: date
    date_to: date
    tasks: list[CleaningTaskRowOut]


class CleaningPhotoOut(BaseModel):
    id: int
    slot: str
    outcome: Optional[str]
    refusal_code: Optional[str]
    trust_level: Optional[str]
    received_at: datetime
    client_captured_at: Optional[datetime]
    has_file: bool


class CleaningEventOut(BaseModel):
    kind: str
    actor_id: Optional[int]
    from_status: Optional[str]
    to_status: Optional[str]
    reason: Optional[str]
    payload: Optional[dict[str, Any]]
    created_at: Optional[datetime]


class CleaningComplaintOut(BaseModel):
    id: int
    building_id: int
    entrance: int
    work_date: date
    author_id: int
    task_id: Optional[int]
    request_number: Optional[str]
    outcome: str
    created_at: Optional[datetime]


class CleaningTaskCardOut(BaseModel):
    task: CleaningTaskRowOut
    version: int
    works: list[str]
    slots_required: list[str]
    session_opened_at: Optional[datetime]
    current: list[CleaningPhotoOut]
    evidence: list[CleaningPhotoOut]
    other: list[CleaningPhotoOut]
    events: list[CleaningEventOut]
    complaints: list[CleaningComplaintOut]


class CleaningDecisionIn(BaseModel):
    to: Literal["accepted", "rejected", "in_progress", "review"]
    version: int = Field(ge=1)
    comment: Optional[str] = Field(default=None, max_length=1000)


class CleaningResponsibleIn(BaseModel):
    user_id: int = Field(ge=1, le=DB_ID_MAX)


class CleaningComplaintDecisionIn(BaseModel):
    outcome: Literal["confirmed", "unfounded"]


class CleaningComplaintsOut(BaseModel):
    complaints: list[CleaningComplaintOut]


class CleaningTimesheetRowOut(BaseModel):
    user_id: int
    first_name: Optional[str]
    last_name: Optional[str]
    planned: int
    accepted: int
    rejected: int
    expired: int
    missed: int
    complaints: int
    confirmed: int
    percent: int


class CleaningTimesheetOut(BaseModel):
    date_from: date
    date_to: date
    rows: list[CleaningTimesheetRowOut]


def _range(date_from: Optional[date], date_to: Optional[date]) -> tuple[date, date]:
    """По умолчанию — текущая неделя с понедельника; диапазон ограничен."""
    today = business_today()
    first = date_from or today - timedelta(days=today.weekday())
    last = date_to or first + timedelta(days=6)
    if last < first or (last - first).days > MAX_RANGE_DAYS:
        raise HTTPException(status_code=422, detail="bad_range")
    return first, last


def _row(task: CleaningTask, address: str, done: int) -> CleaningTaskRowOut:
    return CleaningTaskRowOut(
        id=task.id, building_id=task.building_id, address=address, entrance=task.entrance,
        work_date=task.work_date, status=task.status, responsible_id=task.responsible_id,
        slots_total=len(task.slots_required or ()), slots_done=done, sampled=task.sampled)


def _photo(photo: CleaningPhoto) -> CleaningPhotoOut:
    return CleaningPhotoOut(
        id=photo.id, slot=photo.slot, outcome=photo.outcome, refusal_code=photo.refusal_code,
        trust_level=photo.trust_level, received_at=photo.received_at,
        client_captured_at=photo.client_captured_at, has_file=photo.media_id is not None)


def _complaint(row: CleaningComplaint) -> CleaningComplaintOut:
    return CleaningComplaintOut(
        id=row.id, building_id=row.building_id, entrance=row.entrance, work_date=row.work_date,
        author_id=row.author_id, task_id=row.task_id, request_number=row.request_number,
        outcome=row.outcome, created_at=row.created_at)


@router.get("/tasks", response_model=CleaningTasksOut)
async def list_tasks(date_from: Optional[date] = Query(None), date_to: Optional[date] = Query(None),
                     status: Optional[str] = Query(None, max_length=20),
                     db: AsyncSession = Depends(get_db), user: User = Depends(_read)):
    """Задания за период (матрица план/факт); ``status=review`` — очередь менеджера."""
    first, last = _range(date_from, date_to)
    stmt = (select(CleaningTask, Building.address).join(Building, Building.id == CleaningTask.building_id)
            .where(CleaningTask.work_date >= first, CleaningTask.work_date <= last)
            .order_by(Building.address, CleaningTask.entrance, CleaningTask.work_date))
    if status:
        stmt = stmt.where(CleaningTask.status == status)
    rows = (await db.execute(stmt)).all()
    done: dict[int, int] = {}
    if rows:
        counts = await db.execute(
            select(CleaningPhoto.task_id, func.count()).where(
                CleaningPhoto.task_id.in_([t.id for t, _ in rows]), CleaningPhoto.is_current.is_(True))
            .group_by(CleaningPhoto.task_id))
        done = dict(counts.all())
    return CleaningTasksOut(date_from=first, date_to=last,
                            tasks=[_row(task, address, done.get(task.id, 0)) for task, address in rows])


@router.get("/tasks/{task_id}", response_model=CleaningTaskCardOut)
async def task_card(task_id: int = TaskId, db: AsyncSession = Depends(get_db), user: User = Depends(_read)):
    try:
        card = await control.card(db, task_id)
    except control.ControlError as exc:
        raise _http(exc) from None
    task = card.task
    return CleaningTaskCardOut(
        task=_row(task, card.address, len(card.current)), version=task.version, works=list(task.works),
        slots_required=list(task.slots_required), session_opened_at=task.session_opened_at,
        current=[_photo(p) for p in card.current], evidence=[_photo(p) for p in card.evidence],
        other=[_photo(p) for p in card.other],
        events=[CleaningEventOut(kind=e.kind, actor_id=e.actor_id, from_status=e.from_status,
                                 to_status=e.to_status, reason=e.reason, payload=e.payload,
                                 created_at=e.created_at) for e in card.events],
        complaints=[_complaint(c) for c in card.complaints])


@router.post("/tasks/{task_id}/decision", response_model=CleaningTaskRowOut)
async def decide(body: CleaningDecisionIn, task_id: int = TaskId, db: AsyncSession = Depends(get_db),
                 user: User = Depends(_manage)):
    """Принять / отклонить / вернуть на досъёмку / открыть повторно. 409 ``stale`` — задание изменилось."""
    try:
        task = await control.decide(db, task_id, to=body.to, actor_id=user.id, version=body.version,
                                    comment=body.comment)
    except control.ControlError as exc:
        raise _http(exc) from None
    await db.commit()
    return _row(task, "", 0)


@router.put("/tasks/{task_id}/responsible", status_code=204)
async def set_responsible(body: CleaningResponsibleIn, task_id: int = TaskId,
                          db: AsyncSession = Depends(get_db), user: User = Depends(_manage)):
    """Срочная замена ответственного у одного задания (болезнь в день уборки)."""
    try:
        await control.reassign(db, task_id, user_id=body.user_id, actor_id=user.id)
    except control.ControlError as exc:
        raise _http(exc) from None
    await db.commit()
    return Response(status_code=204)


@router.get("/photos/{photo_id}/file")
async def photo_file(photo_id: int = Path(ge=1, le=DB_ID_MAX), db: AsyncSession = Depends(get_db),
                     user: User = Depends(_read)):
    """Файл любого фото уборки для проверки. Без кэша."""
    from uk_management_bot.api.cleaning.router_exec import _download

    photo = await db.get(CleaningPhoto, photo_id)
    if photo is None or photo.media_id is None:
        raise HTTPException(status_code=404, detail="not_found")
    await db.close()
    file = await _download(photo.media_id)
    if file is None:
        raise HTTPException(status_code=503, detail="media_unavailable")
    return Response(content=file[0], media_type=file[1], headers={"Cache-Control": "no-store"})


@router.get("/complaints", response_model=CleaningComplaintsOut)
async def list_complaints(date_from: Optional[date] = Query(None), date_to: Optional[date] = Query(None),
                          db: AsyncSession = Depends(get_db), user: User = Depends(_read)):
    first, last = _range(date_from, date_to)
    rows = await db.execute(
        select(CleaningComplaint).where(CleaningComplaint.work_date >= first, CleaningComplaint.work_date <= last)
        .order_by(CleaningComplaint.id.desc()))
    return CleaningComplaintsOut(complaints=[_complaint(c) for c in rows.scalars()])


@router.post("/complaints/{complaint_id}/decision", response_model=CleaningComplaintOut)
async def decide_complaint(body: CleaningComplaintDecisionIn, complaint_id: int = Path(ge=1, le=DB_ID_MAX),
                           db: AsyncSession = Depends(get_db), user: User = Depends(_manage)):
    row = await complaints.decide(db, complaint_id, outcome=body.outcome, actor_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="not_found")
    await db.commit()
    return _complaint(row)


@router.get("/timesheet", response_model=CleaningTimesheetOut)
async def timesheet(date_from: Optional[date] = Query(None), date_to: Optional[date] = Query(None),
                    db: AsyncSession = Depends(get_db), user: User = Depends(_read)):
    first, last = _range(date_from, date_to)
    rows = await control.timesheet(db, first, last)
    names = {}
    if rows:
        found = await db.execute(select(User.id, User.first_name, User.last_name)
                                 .where(User.id.in_([r.user_id for r in rows])))
        names = {uid: (first_name, last_name) for uid, first_name, last_name in found.all()}
    return CleaningTimesheetOut(date_from=first, date_to=last, rows=[
        CleaningTimesheetRowOut(
            user_id=r.user_id, first_name=names.get(r.user_id, (None, None))[0],
            last_name=names.get(r.user_id, (None, None))[1], planned=r.planned, accepted=r.accepted,
            rejected=r.rejected, expired=r.expired, missed=r.missed, complaints=r.complaints,
            confirmed=r.confirmed, percent=r.percent) for r in rows])
