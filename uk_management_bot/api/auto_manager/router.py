"""API конфига автоматического менеджера (dashboard).

В отличие от `board_config`, здесь ОБА маршрута приватные: GET и PUT доступны
роли manager ИЛИ admin (`require_action("auto_manager.configure")` — OR-семантика,
см. `api/dependencies.py::require_roles`). Загрузка/сохранение целиком
делегированы `services/auto_manager/config.py` (async `load_config`/
`save_config`) — не дублируем здесь DEFAULT_CONFIG/upsert-логику, она уже
реализована и протестирована там (используется и API, и ботом).
"""
import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.auto_manager.schemas import AutoManagerConfigData
from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.user import User
from uk_management_bot.services.auto_manager.config import load_config, save_config

logger = logging.getLogger(__name__)

router = APIRouter()


def _response(data: dict) -> AutoManagerConfigData:
    """Конфиг + read-only доступность ИИ-режима (деплой-флаг площадки)."""
    return AutoManagerConfigData.model_validate(
        {**data, "ai_available": settings.AI_MANAGER_ENABLED}
    )


@router.get("/auto-manager-config", response_model=AutoManagerConfigData)
async def get_auto_manager_config(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_action("auto_manager.configure")),
) -> AutoManagerConfigData:
    """Текущий конфиг авто-менеджера. Доступен manager ИЛИ admin.

    Толерантен к отсутствующей строке/таблице (миграция не накатана) — отдаёт
    дефолт вместо падения (см. `load_config`)."""
    data = await load_config(db)
    return _response(data)


@router.put("/auto-manager-config", response_model=AutoManagerConfigData)
@limiter.limit("30/minute")
async def update_auto_manager_config(
    request: Request,
    payload: AutoManagerConfigData,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_action("auto_manager.configure")),
) -> AutoManagerConfigData:
    """Сохранить конфиг авто-менеджера. Доступен manager ИЛИ admin.

    Write-side rate-limit 30/min зеркалит `board_config`'s PUT (SEC-084) —
    та же защита от churn конфига украденным токеном."""
    saved = await save_config(db, payload.config_dict(), updated_by=user.id)
    logger.info("auto_manager_config обновлён пользователем %s", user.id)
    return _response(saved)
