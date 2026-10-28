"""API мониторинга отключений: ``/api/v2/news-watch`` (dashboard + юзербот).

DARK: ``settings.NEWS_WATCH_ENABLED=False`` → весь роутер отвечает единым 404
(паттерн elevators). ⚠️ Новый префикс — на проде InfraSafe edge требует
добавления в allowlist ДО включения.

Менеджер (``board.configure`` — те же руки, что публикуют объявления на
табло): конфиг, очередь, publish/reject/retry-broadcast. Юзербот
(``X-Service-Token`` = NEWS_WATCH_SERVICE_TOKEN, fail-closed при пустом):
``POST /inbox``, ``GET /sources``.
"""
from __future__ import annotations

import hmac
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.api.news_watch.schemas import (
    InboxIn,
    InboxOut,
    NewsItemOut,
    NewsItemsOut,
    NewsWatchConfigData,
    SourcesOut,
)
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.news_item import NEWS_STATUSES, NewsItem
from uk_management_bot.database.models.user import User
from uk_management_bot.services.news_watch import pipeline
from uk_management_bot.services.news_watch.config import load_config, save_config

logger = logging.getLogger(__name__)


async def _require_enabled() -> None:
    if not settings.NEWS_WATCH_ENABLED:
        raise HTTPException(status_code=404, detail="Not Found")


async def _require_service_token(x_service_token: Optional[str] = Header(default=None)) -> None:
    """Юзербот: сервисный токен. Пустой настроенный токен → 401 (fail-closed)."""
    expected = settings.NEWS_WATCH_SERVICE_TOKEN
    if not expected or not x_service_token or not hmac.compare_digest(x_service_token, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


router = APIRouter(dependencies=[Depends(_require_enabled)])
_manager = require_action("board.configure")


# ── конфиг ────────────────────────────────────────────────────────────

@router.get("/config", response_model=NewsWatchConfigData)
async def get_config(db: AsyncSession = Depends(get_db), user: User = Depends(_manager)):
    return NewsWatchConfigData.model_validate(await load_config(db))


@router.put("/config", response_model=NewsWatchConfigData)
@limiter.limit("30/minute")
async def put_config(request: Request, payload: NewsWatchConfigData,
                     db: AsyncSession = Depends(get_db), user: User = Depends(_manager)):
    saved = await save_config(db, payload.model_dump(), updated_by=user.id)
    logger.info("news_watch_config обновлён пользователем %s", user.id)
    return NewsWatchConfigData.model_validate(saved)


# ── очередь и решения ─────────────────────────────────────────────────

@router.get("/items", response_model=NewsItemsOut)
async def list_items(status: str = Query(default="pending"), limit: int = Query(default=50, ge=1, le=200),
                     db: AsyncSession = Depends(get_db), user: User = Depends(_manager)):
    if status not in NEWS_STATUSES:
        raise HTTPException(status_code=422, detail=f"status: ожидается одно из {list(NEWS_STATUSES)}")
    total = (await db.execute(select(func.count()).select_from(NewsItem).where(NewsItem.status == status))).scalar_one()
    rows = (await db.execute(
        select(NewsItem).where(NewsItem.status == status).order_by(NewsItem.id.desc()).limit(limit)
    )).scalars().all()
    return NewsItemsOut(items=[NewsItemOut.model_validate(r) for r in rows], total=int(total))


def _translate(e: pipeline.NewsWatchError) -> HTTPException:
    status = 404 if "не найдена" in str(e) else 409
    return HTTPException(status_code=status, detail=str(e))


@router.post("/items/{item_id}/publish", response_model=NewsItemOut)
@limiter.limit("30/minute")
async def publish_item(request: Request, item_id: int, db: AsyncSession = Depends(get_db),
                       user: User = Depends(_manager)):
    try:
        return NewsItemOut.model_validate(await pipeline.publish(db, item_id, user_id=user.id))
    except pipeline.NewsWatchError as e:
        raise _translate(e) from None


@router.post("/items/{item_id}/reject", response_model=NewsItemOut)
@limiter.limit("30/minute")
async def reject_item(request: Request, item_id: int, db: AsyncSession = Depends(get_db),
                      user: User = Depends(_manager)):
    try:
        return NewsItemOut.model_validate(await pipeline.reject(db, item_id, user_id=user.id))
    except pipeline.NewsWatchError as e:
        raise _translate(e) from None


@router.post("/items/{item_id}/retry-broadcast", response_model=NewsItemOut)
@limiter.limit("30/minute")
async def retry_item_broadcast(request: Request, item_id: int, db: AsyncSession = Depends(get_db),
                               user: User = Depends(_manager)):
    try:
        return NewsItemOut.model_validate(await pipeline.retry_broadcast(db, item_id))
    except pipeline.NewsWatchError as e:
        raise _translate(e) from None


# ── юзербот ───────────────────────────────────────────────────────────

@router.post("/inbox", response_model=InboxOut, dependencies=[Depends(_require_service_token)])
@limiter.limit("120/minute")
async def inbox(request: Request, payload: InboxIn, db: AsyncSession = Depends(get_db)):
    try:
        item, created = await pipeline.ingest(db, pipeline.Inbound(
            source_chat_id=payload.source_chat_id, source_message_id=payload.source_message_id,
            chat_title=payload.chat_title, text=payload.text, posted_at=payload.posted_at,
        ))
    except pipeline.NewsWatchError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return InboxOut(id=item.id, status=item.status, created=created)


@router.get("/sources", response_model=SourcesOut, dependencies=[Depends(_require_service_token)])
async def sources(db: AsyncSession = Depends(get_db)):
    cfg = await load_config(db)
    return SourcesOut(sources=cfg["sources"])
