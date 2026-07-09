"""API конфига публичной витрины resident-board.

- `GET /api/v2/public/board-config`  — без аутентификации, отдаёт конфиг странице.
- `PUT /api/v2/board-config`         — только менеджер, сохраняет правки.

Кэш намеренно не используется: конфиг — одна строка с PK-доступом, запрос
тривиально дёшев, а per-worker кэш при `--workers 2` отдавал бы устаревшие
данные с одного воркера после правки на другом.
"""
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.board_config.schemas import BoardConfigData
from uk_management_bot.api.board_config.service import CONFIG_ROW_ID, load_board_config
from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.database.models.board_config import BoardConfig
from uk_management_bot.database.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/public/board-config", response_model=BoardConfigData)
@limiter.limit("120/minute")
async def get_board_config(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BoardConfigData:
    """Конфиг витрины для публичной страницы. Без аутентификации.

    Если строки ещё нет (миграция не накатана) — отдаём дефолт, страница
    не должна белеть.
    """
    return await load_board_config(db)


@router.put("/board-config", response_model=BoardConfigData)
@limiter.limit("30/minute")
async def update_board_config(
    request: Request,
    payload: BoardConfigData,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
) -> BoardConfigData:
    """Сохранить конфиг витрины. Только для роли manager.

    SEC-084: write-side rate-limit (30/min per client IP) — mirrors the GET
    limit so a stolen manager token can't churn config writes."""
    data = payload.model_dump()

    result = await db.execute(select(BoardConfig).where(BoardConfig.id == CONFIG_ROW_ID))
    row = result.scalar_one_or_none()
    if row is None:
        db.add(BoardConfig(id=CONFIG_ROW_ID, data=data, updated_by=user.id))
    else:
        row.data = data
        row.updated_by = user.id
    await db.commit()

    logger.info("board_config обновлён пользователем %s", user.id)
    return payload
