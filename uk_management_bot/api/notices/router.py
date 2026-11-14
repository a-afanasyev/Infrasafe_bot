"""API раздела «Новости и уведомления»: ``/api/v2/notices``.

Менеджер (``notices.manage``) ведёт ленту: новости и плановые отключения,
отложенная публикация, срок показа. Жители эти записи получают прежними
списками витрины (services/notices/board.py), отдельного публичного
эндпоинта у раздела нет.

⚠️ Новый префикс — на проде InfraSafe edge требует добавления в allowlist ДО
выкатки (обе площадки).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.api.notices.schemas import NoticeCreateIn, NoticeIn, NoticeOut, NoticesOut
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.database.models.notice import NOTICE_KINDS, NOTICE_STATUSES, Notice
from uk_management_bot.database.models.user import User
from uk_management_bot.services.notices import service

logger = logging.getLogger(__name__)

router = APIRouter()
_manager = require_action("notices.manage")


def _out(notice: Notice) -> NoticeOut:
    return NoticeOut.model_validate({
        **{c.name: getattr(notice, c.name) for c in Notice.__table__.columns},
        "scope_ids": list(notice.scope_ids or []),
        "state": service.state_of(notice),
    })


async def _run(coro) -> Notice:
    """Ошибки жизненного цикла → 404 / 409 с текстом для менеджера."""
    try:
        return await coro
    except service.NoticeNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except service.NoticeError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.get("", response_model=NoticesOut)
@limiter.limit("120/minute")
async def list_notices(
    request: Request,
    kind: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    period_from: Optional[datetime] = Query(default=None, alias="from"),
    period_to: Optional[datetime] = Query(default=None, alias="to"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager),
) -> NoticesOut:
    """Лента; с ``from``/``to`` — записи окна календаря."""
    if kind is not None and kind not in NOTICE_KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {NOTICE_KINDS}")
    if status is not None and status not in NOTICE_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {NOTICE_STATUSES}")
    items, total = await service.list_notices(
        db, kind=kind, status=status, period_from=period_from, period_to=period_to,
        limit=limit, offset=offset,
    )
    return NoticesOut(items=[_out(n) for n in items], total=total)


@router.post("", response_model=NoticeOut, status_code=201)
@limiter.limit("30/minute")
async def create_notice(
    request: Request,
    payload: NoticeCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager),
) -> NoticeOut:
    fields = payload.model_dump(exclude={"publish"}, exclude_none=True)
    notice = await _run(service.create_notice(db, fields, user_id=user.id, publish=payload.publish))
    logger.info("notice %s создана пользователем %s (publish=%s)", notice.id, user.id, payload.publish)
    return _out(notice)


@router.patch("/{notice_id}", response_model=NoticeOut)
@limiter.limit("30/minute")
async def update_notice(
    request: Request,
    notice_id: int,
    payload: NoticeIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager),
) -> NoticeOut:
    """Правка. Поле, присланное как null, очищается (например, срок показа)."""
    fields = payload.model_dump(include=payload.model_fields_set)
    for required in ("kind", "title_ru", "title_uz", "text_ru", "text_uz", "place_ru", "place_uz",
                     "icon", "important", "all_day", "scope", "scope_ids"):
        if required in fields and fields[required] is None:
            raise HTTPException(status_code=422, detail=f"{required} must not be null")
    return _out(await _run(service.update_notice(db, notice_id, fields)))


@router.post("/{notice_id}/publish", response_model=NoticeOut)
@limiter.limit("30/minute")
async def publish_notice(
    request: Request,
    notice_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager),
) -> NoticeOut:
    notice = await _run(service.publish_notice(db, notice_id))
    logger.info("notice %s опубликована пользователем %s", notice.id, user.id)
    return _out(notice)


@router.post("/{notice_id}/close", response_model=NoticeOut)
@limiter.limit("30/minute")
async def close_notice(
    request: Request,
    notice_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager),
) -> NoticeOut:
    notice = await _run(service.close_notice(db, notice_id, user_id=user.id))
    logger.info("notice %s закрыта пользователем %s", notice.id, user.id)
    return _out(notice)


@router.delete("/{notice_id}", status_code=204)
@limiter.limit("30/minute")
async def delete_notice(
    request: Request,
    notice_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager),
) -> Response:
    await _run(service.delete_notice(db, notice_id))
    return Response(status_code=204)
