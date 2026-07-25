"""API конфига публичной витрины resident-board.

- `GET /api/v2/public/board-config`  — без аутентификации, отдаёт конфиг странице.
- `PUT /api/v2/board-config`         — только менеджер, сохраняет правки.

Кэш намеренно не используется: конфиг — одна строка с PK-доступом, запрос
тривиально дёшев, а per-worker кэш при `--workers 2` отдавал бы устаревшие
данные с одного воркера после правки на другом.
"""
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.board_config.schemas import BoardConfigResponse, BoardConfigUpdateIn
from uk_management_bot.api.board_config.service import (
    load_board_config,
    merge_and_save_board_config,
    to_public_response,
)
from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.database.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/public/board-config", response_model=BoardConfigResponse)
@limiter.limit("120/minute")
async def get_board_config(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BoardConfigResponse:
    """Конфиг витрины для публичной страницы. Без аутентификации.

    Если строки ещё нет (миграция не накатана) — отдаём дефолт, страница
    не должна белеть.
    """
    cfg = await load_board_config(db)
    return to_public_response(cfg)


@router.put("/board-config", response_model=BoardConfigResponse)
@limiter.limit("30/minute")
async def update_board_config(
    request: Request,
    payload: BoardConfigUpdateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
) -> BoardConfigResponse:
    """Сохранить конфиг витрины. Только для роли manager.

    SEC-084: write-side rate-limit (30/min per client IP) — mirrors the GET
    limit so a stolen manager token can't churn config writes.

    Отдаём результат реального мёржа (`to_public_response(merged)`), а не
    `payload` как раньше — старый код возвращал клиенту его же сырое
    непромёрженное тело вместо того, что реально сохранилось."""
    updates = payload.model_dump(mode="json", include=payload.model_fields_set)
    merged = await merge_and_save_board_config(db, updates, user.id)

    logger.info("board_config обновлён пользователем %s", user.id)
    return to_public_response(merged)
