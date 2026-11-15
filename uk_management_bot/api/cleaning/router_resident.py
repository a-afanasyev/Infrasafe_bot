"""Жителям: открытая сводка уборки (``/api/v2/public/cleaning``) и жалоба.

Открытые маршруты без входа: счёт по домам, дом по подъездам, фото публичных
точек. При выключенном модуле сводка отвечает пустым 200 (табло в холле
опрашивает постоянно — стабильное «ничего нет» ему удобнее ошибок), остальное — 404.

Жалоба (``POST /api/v2/cleaning/complaints``) — только на свой дом. Сначала
в одной транзакции пишется жалоба и принятое задание уходит на проверку; заявка
создаётся следом, её сбой жалобу не отменяет — повтор запроса досоздаёт заявку.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.cleaning import CleaningTask
from uk_management_bot.database.models.user import User
from uk_management_bot.services.cleaning import complaints, public
from uk_management_bot.services.cleaning.assignments import is_cleaner
from uk_management_bot.services.request_address import AddressResolutionError, resolve_request_address_async
from uk_management_bot.utils.business_time import business_today, fmt_date

logger = logging.getLogger(__name__)
DB_ID_MAX = 2_147_483_647

public_router = APIRouter()
router = APIRouter()


def _enabled() -> bool:
    return bool(settings.CLEANING_ENABLED)


def _or_404() -> None:
    if not _enabled():
        raise HTTPException(status_code=404, detail="Not Found")


class CleaningPublicEntranceOut(BaseModel):
    entrance: int
    state: str
    done_at: Optional[datetime]
    photo_ids: list[int]


class CleaningPublicBuildingOut(BaseModel):
    building_id: int
    address: str
    state: str
    done_at: Optional[datetime]
    entrances: list[CleaningPublicEntranceOut]


class CleaningPublicTodayOut(BaseModel):
    enabled: bool
    work_date: date
    buildings_total: int
    buildings_done: int
    buildings: list[CleaningPublicBuildingOut]


class CleaningPublicBuildingViewOut(BaseModel):
    building_id: int
    address: str
    entrance_count: int
    work_date: date
    entrances: list[CleaningPublicEntranceOut]
    week: list[list[dict]]


class CleaningComplaintIn(BaseModel):
    building_id: int = Field(ge=1, le=DB_ID_MAX)
    entrance: int = Field(ge=1, le=50)


class CleaningComplaintCreatedOut(BaseModel):
    id: int
    request_number: Optional[str]


# ── открытые маршруты ───────────────────────────────────────────────────────

def _entrance_out(e: public.EntranceToday) -> CleaningPublicEntranceOut:
    return CleaningPublicEntranceOut(entrance=e.entrance, state=e.state, done_at=e.done_at, photo_ids=e.photo_ids)


@public_router.get("/cleaning/today", response_model=CleaningPublicTodayOut)
@limiter.limit("300/minute")
async def cleaning_today(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """«Уборка сегодня»: счёт по домам. Дом убран, когда приняты все его задания дня."""
    day = business_today()
    if not _enabled():
        return CleaningPublicTodayOut(enabled=False, work_date=day, buildings_total=0, buildings_done=0, buildings=[])
    rows = await public.today(db, day)
    scheduled = [r for r in rows if r.state != "none"]
    response.headers["Cache-Control"] = "public, max-age=60"
    return CleaningPublicTodayOut(
        enabled=True, work_date=day, buildings_total=len(scheduled),
        buildings_done=sum(r.state == "done" for r in scheduled),
        buildings=[CleaningPublicBuildingOut(
            building_id=r.building_id, address=r.address, state=r.state, done_at=r.done_at,
            entrances=[_entrance_out(e) for e in r.entrances]) for r in rows])


@public_router.get("/cleaning/buildings/{building_id}", response_model=CleaningPublicBuildingViewOut)
@limiter.limit("300/minute")
async def cleaning_building(request: Request, building_id: int = Path(ge=1, le=DB_ID_MAX), db: AsyncSession = Depends(get_db)):
    _or_404()
    day = business_today()
    view = await public.building_view(db, building_id, day)
    if view is None:
        raise HTTPException(status_code=404, detail="Not Found")
    return CleaningPublicBuildingViewOut(
        building_id=view.building_id, address=view.address, entrance_count=view.entrance_count, work_date=day,
        entrances=[_entrance_out(e) for e in view.entrances],
        week=view.week)


@public_router.get("/cleaning/photos/{photo_id}")
@limiter.limit("120/minute")
async def cleaning_photo(request: Request, photo_id: int = Path(ge=1, le=DB_ID_MAX),
                         original: bool = Query(False, description="true — оригинал, иначе превью"),
                         db: AsyncSession = Depends(get_db)):
    """Текущее фото принятого сегодняшнего задания: превью для миниатюр, оригинал по нажатию.

    Проверки — на каждый запрос, без кэша.
    """
    from uk_management_bot.api.cleaning.router_exec import _download

    _or_404()
    photo = await public.public_photo(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Not Found")
    await db.close()
    file = await _download(photo.media_id, not original)
    if file is None:
        raise HTTPException(status_code=503, detail="media_unavailable")
    return Response(content=file[0], media_type=file[1], headers={"Cache-Control": "no-store"})


# ── жалоба ──────────────────────────────────────────────────────────────────

async def _create_request(db: AsyncSession, user: User, building_id: int, entrance: int, work_date: date,
                          executor_id: Optional[int] = None, schedule_notify=None) -> str:
    """Заявка категории «Уборка» на дом жителя; возвращает её номер.

    ``executor_id`` — уборщица этого подъезда: заявка сразу назначается ей, а не
    дежурному и не группе (кто убирал, тот и переделывает).
    """
    from uk_management_bot.api.requests import service as requests_service
    from uk_management_bot.utils.constants import URGENCY_DEFAULT

    resolved = await resolve_request_address_async(db, user.id, "applicant", "building", building_id)
    persisted = await requests_service.persist_request(
        db, user_id=user.id, category="cleaning", urgency=URGENCY_DEFAULT,
        description=f"Жалоба на уборку: подъезд {entrance}, {fmt_date(work_date)}",
        source="twa", resolved=resolved, webhook_tag="twa", preferred_executor_id=executor_id,
        schedule_notify=schedule_notify)
    return persisted.request.request_number


@router.post("/complaints", response_model=CleaningComplaintCreatedOut, status_code=201,
             dependencies=[Depends(_or_404)])
@limiter.limit("10/minute")
async def file_complaint(request: Request, body: CleaningComplaintIn, background: BackgroundTasks,
                         db: AsyncSession = Depends(get_db),
                         user: User = Depends(require_action("requests.create"))):
    """«Не убрано»: жалоба на подъезд своего дома за сегодня. Повтор безопасен."""
    try:
        await resolve_request_address_async(db, user.id, "applicant", "building", body.building_id)
    except AddressResolutionError as exc:
        raise HTTPException(status_code=exc.status_code, detail="building_not_allowed") from None
    building = await db.get(Building, body.building_id)
    if building is None or body.entrance > building.entrance_count:
        raise HTTPException(status_code=422, detail="bad_entrance")

    day = business_today()
    try:
        complaint = await complaints.file_complaint(
            db, author_id=user.id, building_id=body.building_id, entrance=body.entrance, work_date=day)
    except complaints.ComplaintLimit:
        raise HTTPException(status_code=429, detail="too_many_complaints") from None
    complaint_id, number = complaint.id, complaints.request_number_of(complaint)
    task = await db.get(CleaningTask, complaint.task_id) if complaint.task_id is not None else None
    # Заявку ведёт уборщица подъезда — если она по-прежнему уборщица (не заблокирована, роль и
    # специализация на месте); иначе заявка идёт обычным порядком категории.
    responsible = await db.get(User, task.responsible_id) if task is not None and task.responsible_id else None
    cleaner_id = responsible.id if is_cleaner(responsible) else None
    claimed = await complaints.claim_request(db, complaint_id)
    await db.commit()  # жалоба, перевод на проверку и отметка «заявка создаётся» — до самой заявки

    if claimed:
        try:
            number = await _create_request(db, user, body.building_id, body.entrance, day, cleaner_id,
                                           schedule_notify=background.add_task)
            await complaints.attach_request(db, complaint_id, number)
            await db.commit()
        except Exception as exc:  # noqa: BLE001 — заявка вторична: жалоба уже записана
            await db.rollback()
            await complaints.release_request(db, complaint_id)
            await db.commit()
            number = None
            logger.error("cleaning: заявка по жалобе %s не создана: %s", complaint_id, type(exc).__name__)
    return CleaningComplaintCreatedOut(id=complaint_id, request_number=number)
