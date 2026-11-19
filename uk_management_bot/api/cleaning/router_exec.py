"""API уборщицы: ``/api/v2/cleaning`` — задания на сегодня и фото этажей.

Задание видит и ведёт только его ответственный. Фото точки — и есть отметка
«этаж помыт»; протокол загрузки (ключ операции, аренда, финализация, поздние
доказательства) — в ``services/cleaning/uploads.py``. Здесь только транспорт.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Path, Query, Request, Response, UploadFile,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.cleaning import CleaningDay, CleaningPhoto, CleaningTask
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import AsyncSessionLocal
from uk_management_bot.services.cleaning import days, uploads
from uk_management_bot.services.cleaning.uploads import UploadRefused, _media_upload
from uk_management_bot.services.executor_completion import COMPLETION_PHOTO_MAX_BYTES
from uk_management_bot.utils.business_time import business_today

DB_ID_MAX = 2_147_483_647
# До 16 этажей подряд на подъезд плюс повторы очереди при плохой связи.
PHOTO_RATE_LIMIT = "120/minute"


async def _require_enabled() -> None:
    if not settings.CLEANING_ENABLED:
        raise HTTPException(status_code=404, detail="Not Found")


router = APIRouter(dependencies=[Depends(_require_enabled)])
_cleaner = require_action("cleaning.work")
TaskId = Path(ge=1, le=DB_ID_MAX)


class CleaningSlotOut(BaseModel):
    slot: str
    done: bool
    photo_id: Optional[int]
    captured_at: Optional[datetime]


class CleaningMyTaskOut(BaseModel):
    id: int
    building_id: int
    address: str
    entrance: int
    works: list[str]
    status: str
    version: int
    session_open: bool
    slots: list[CleaningSlotOut]


class CleaningMyTasksOut(BaseModel):
    work_date: date
    day_end_at: Optional[datetime]
    tasks: list[CleaningMyTaskOut]


class CleaningUploadOut(BaseModel):
    photo_id: int
    outcome: str
    refusal_code: Optional[str]
    replay: bool
    task_status: str


async def _download(media_id: int, preview: bool = False) -> Optional[tuple[bytes, str]]:
    """Файл фото: превью (миниатюры, быстро из кэша) или оригинал (просмотр по нажатию)."""
    from uk_management_bot.integrations import get_media_client

    client = get_media_client()
    return await client.download_media_file(media_id, preview=preview) if client is not None else None


async def _warm_preview(media_id: int) -> None:
    """Построить превью сразу после загрузки: первый зритель не ждёт Telegram. Не бросает."""
    from uk_management_bot.integrations import get_media_client

    client = get_media_client()
    if client is not None:
        await client.warm_previews([media_id])


async def _own_task(db: AsyncSession, task_id: int, user: User) -> CleaningTask:
    task = await db.get(CleaningTask, task_id)
    if task is None or task.responsible_id != user.id:
        raise HTTPException(status_code=404, detail="not_found")
    return task


@router.get("/my/tasks", response_model=CleaningMyTasksOut)
async def my_tasks(db: AsyncSession = Depends(get_db), user: User = Depends(_cleaner)):
    """Мои задания на сегодня. Задания дня создаются здесь, если тик ещё не успел."""
    today = business_today()
    await days.ensure_tasks(db, today)
    await db.commit()
    day = await db.get(CleaningDay, today)
    rows = (await db.execute(
        select(CleaningTask, Building.address).join(Building, Building.id == CleaningTask.building_id)
        .where(CleaningTask.work_date == today, CleaningTask.responsible_id == user.id)
        .order_by(Building.address, CleaningTask.entrance)
    )).all()
    current: dict[tuple[int, str], CleaningPhoto] = {}
    if rows:
        photos = await db.execute(select(CleaningPhoto).where(
            CleaningPhoto.task_id.in_([task.id for task, _ in rows]), CleaningPhoto.is_current.is_(True)))
        current = {(p.task_id, p.slot): p for p in photos.scalars()}
    return CleaningMyTasksOut(
        work_date=today, day_end_at=day.day_end_at if day is not None else None,
        tasks=[
            CleaningMyTaskOut(
                id=task.id, building_id=task.building_id, address=address, entrance=task.entrance,
                works=list(task.works), status=task.status, version=task.version,
                session_open=task.session_opened_at is not None,
                slots=[CleaningSlotOut(
                    slot=slot, done=(photo := current.get((task.id, slot))) is not None,
                    photo_id=photo.id if photo else None,
                    captured_at=photo.client_captured_at if photo else None,
                ) for slot in task.slots_required],
            ) for task, address in rows
        ],
    )


@router.post("/tasks/{task_id}/session", status_code=204)
async def open_session(task_id: int = TaskId, db: AsyncSession = Depends(get_db),
                       user: User = Depends(_cleaner)):
    """Первое онлайн-открытие задания: от него считается окно доверия ``live``."""
    await _own_task(db, task_id, user)
    await uploads.open_session(db, task_id, user.id)
    await db.commit()
    return Response(status_code=204)


@router.post("/tasks/{task_id}/photos", response_model=CleaningUploadOut)
@limiter.limit(PHOTO_RATE_LIMIT)
async def upload_photo(
    request: Request,
    background: BackgroundTasks,
    task_id: int = TaskId,
    photo: UploadFile = File(..., description="Кадр точки: JPEG/PNG, до 8 МиБ"),
    slot: str = Form(..., max_length=40, description="floor:N или point:name из задания"),
    op_key: str = Form(..., description="UUID операции; повтор с ним же возвращает сохранённый исход"),
    captured_at: Optional[datetime] = Form(None, description="Время съёмки на телефоне (для порядка пересъёмок)"),
    source: str = Form("live", max_length=10, description="live — камера приложения, system — системная камера"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_cleaner),
):
    """Фото точки задания.

    200 — исход операции: ``activated`` / ``superseded`` / ``evidence`` / ``refused``
    (с ``refusal_code``: ``not_yours``, ``bad_slot``, ``frozen``, ``too_late``, ``bad_photo``).
    404 — задания нет; 409 ``key_reused`` / ``in_progress`` (повторить); 413/415/422 — файл,
    ключ, формат точки; 503 ``media_unavailable`` (повторить).
    """
    photo_bytes = await photo.read(COMPLETION_PHOTO_MAX_BYTES + 1)
    await db.close()  # сервис открывает свои сессии; не держим транзакцию через загрузку
    try:
        result = await uploads.upload_photo(
            AsyncSessionLocal, user_id=user.id, task_id=task_id, slot=slot, op_key=op_key,
            photo_bytes=photo_bytes, client_captured_at=captured_at, media_upload=_media_upload,
            system_camera=source != "live")
    except UploadRefused as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.code) from None
    if result.media_id is not None and not result.replay:
        background.add_task(_warm_preview, result.media_id)
    async with AsyncSessionLocal() as fresh:
        task = await fresh.get(CleaningTask, task_id)
    return CleaningUploadOut(photo_id=result.photo_id, outcome=result.outcome, refusal_code=result.refusal_code,
                             replay=result.replay, task_status=task.status)


@router.get("/tasks/{task_id}/photos/{photo_id}/file")
async def my_photo_file(task_id: int = TaskId, photo_id: int = Path(ge=1, le=DB_ID_MAX),
                        original: bool = Query(False, description="true — оригинал, иначе превью"),
                        db: AsyncSession = Depends(get_db), user: User = Depends(_cleaner)):
    """Своё фото точки (предпросмотр снятого). Без кэша: пересъёмка видна сразу."""
    await _own_task(db, task_id, user)
    photo = await db.get(CleaningPhoto, photo_id)
    if photo is None or photo.task_id != task_id or photo.media_id is None:
        raise HTTPException(status_code=404, detail="not_found")
    await db.close()
    file = await _download(photo.media_id, not original)
    if file is None:
        raise HTTPException(status_code=503, detail="media_unavailable")
    body, content_type = file
    return Response(content=body, media_type=content_type, headers={"Cache-Control": "no-store"})
