"""API раздела «Новости и уведомления»: ``/api/v2/board-config/notices``.

Менеджер (``notices.manage``) ведёт ленту: новости и плановые отключения,
отложенная публикация, срок показа. Жители эти записи получают прежними
списками витрины (services/notices/board.py), отдельного публичного
эндпоинта у раздела нет.

Префикс намеренно вложен в ``/api/v2/board-config``: edge обеих площадок
пропускает его целиком (проверено пробами 2026-11-15, включая PATCH/DELETE), а
новый верхний префикс пришлось бы заявлять в allowlist у владельца edge.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.api.notices.schemas import (
    DB_ID_MAX, AudienceOut, NoticeCreateIn, NoticeIn, NoticeOut, NoticesOut, NoticeScope, OutageIn,
    OutageNoticeOut, OutageOptionsOut,
)
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.database.models.notice import NOTICE_KINDS, NOTICE_STATUSES, Notice
from uk_management_bot.database.models.user import User
from uk_management_bot.services.notices import outages, service
from uk_management_bot.services.notices.audience import count_recipients, unknown_scope_ids

logger = logging.getLogger(__name__)

router = APIRouter()
_manager = require_action("notices.manage")
_staff = require_action("outages.announce")


def _out(notice: Notice, names: Optional[dict[int, str]] = None) -> NoticeOut:
    names = names or {}
    return NoticeOut.model_validate({
        **{c.name: getattr(notice, c.name) for c in Notice.__table__.columns},
        "scope_ids": list(notice.scope_ids or []),
        "state": service.state_of(notice),
        "created_by_name": names.get(notice.created_by),
        "closed_by_name": names.get(notice.closed_by),
    })


async def _names(db: AsyncSession, notices: list[Notice]) -> dict[int, str]:
    """Имена авторов и закрывших — одним запросом на всю ленту."""
    ids = {uid for n in notices for uid in (n.created_by, n.closed_by) if uid}
    if not ids:
        return {}
    rows = await db.execute(select(User.id, User.first_name, User.last_name).where(User.id.in_(ids)))
    return {uid: " ".join(part for part in (first, last) if part) for uid, first, last in rows.all()}


async def _run(coro) -> Notice:
    """Ошибки жизненного цикла → 404 / 422 / 409 с текстом для менеджера."""
    try:
        return await coro
    except service.NoticeNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except service.NoticeInvalid as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
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
    names = await _names(db, items)
    return NoticesOut(items=[_out(n, names) for n in items], total=total)


@router.get("/audience", response_model=AudienceOut)
@limiter.limit("120/minute")
async def audience(
    request: Request,
    scope: NoticeScope = Query(default="all"),
    ids: list[int] = Query(default_factory=list, max_length=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager),
) -> AudienceOut:
    """Подсказка формы: сколько жителей получит рассылку."""
    if any(not 0 < i <= DB_ID_MAX for i in ids) or await unknown_scope_ids(db, scope, ids):
        raise HTTPException(status_code=422, detail="unknown yard or building id")
    return AudienceOut(count=await count_recipients(db, scope, ids))


def _outage_out(notice: Notice) -> OutageNoticeOut:
    return OutageNoticeOut(
        id=notice.id, resource=notice.resource, title_ru=notice.title_ru, title_uz=notice.title_uz,
        status=notice.status, state=service.state_of(notice), starts_at=notice.starts_at, ends_at=notice.ends_at)


async def _outage(coro) -> Notice:
    try:
        return await coro
    except outages.OutageRefused as e:
        raise HTTPException(status_code=outages.REFUSAL_STATUS.get(e.code, 409), detail=e.code) from e


@router.get("/outages/options", response_model=OutageOptionsOut)
@limiter.limit("60/minute")
async def outage_options(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_staff),
) -> OutageOptionsOut:
    """Экран «Отключил воду»: гейт (сантехник на смене), дома, идущие отключения."""
    data = await outages.options(db, user)
    return OutageOptionsOut(**{**data, "open": [_outage_out(n) for n in data["open"]]})


@router.post("/outages", response_model=OutageNoticeOut, status_code=201)
@limiter.limit("10/minute")
async def announce_outage(
    request: Request,
    payload: OutageIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_staff),
) -> OutageNoticeOut:
    """Сантехник на смене объявляет отключение: жителям домов — сразу, менеджерам копия."""
    notice = await _outage(outages.announce(
        db, user, resource=payload.resource, building_ids=payload.building_ids, duration=payload.duration))
    logger.info("outage %s объявлено пользователем %s", notice.id, user.id)
    return _outage_out(notice)


@router.post("/outages/{notice_id}/close", response_model=OutageNoticeOut)
@limiter.limit("10/minute")
async def close_outage(
    request: Request,
    notice_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_staff),
) -> OutageNoticeOut:
    """«Включили»: запись закрыта, жителям — второе сообщение."""
    notice = await _outage(outages.close(db, user, notice_id))
    logger.info("outage %s закрыто пользователем %s", notice.id, user.id)
    return _outage_out(notice)


@router.post("", response_model=NoticeOut, status_code=201)
@limiter.limit("30/minute")
async def create_notice(
    request: Request,
    payload: NoticeCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager),
) -> NoticeOut:
    fields = payload.model_dump(exclude={"publish", "broadcast"}, exclude_none=True)
    notice = await _run(service.create_notice(
        db, fields, user_id=user.id, publish=payload.publish, broadcast=payload.broadcast))
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
    fields = payload.model_dump(include=payload.model_fields_set - {"broadcast"})
    for required in ("kind", "title_ru", "title_uz", "text_ru", "text_uz", "place_ru", "place_uz",
                     "icon", "important", "all_day", "scope", "scope_ids"):
        if required in fields and fields[required] is None:
            raise HTTPException(status_code=422, detail=f"{required} must not be null")
    return _out(await _run(service.update_notice(db, notice_id, fields, broadcast=payload.broadcast)))


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


@router.post("/{notice_id}/retry-broadcast", response_model=NoticeOut)
@limiter.limit("30/minute")
async def retry_broadcast(
    request: Request,
    notice_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager),
) -> NoticeOut:
    return _out(await _run(service.retry_broadcast(db, notice_id)))


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
