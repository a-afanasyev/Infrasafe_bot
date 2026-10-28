"""API конфига автоматического менеджера (dashboard).

В отличие от `board_config`, здесь ОБА маршрута приватные: GET и PUT доступны
роли manager ИЛИ admin (`require_action("auto_manager.configure")` — OR-семантика,
см. `api/dependencies.py::require_roles`). Загрузка/сохранение целиком
делегированы `services/auto_manager/config.py` (async `load_config`/
`save_config`) — не дублируем здесь DEFAULT_CONFIG/upsert-логику, она уже
реализована и протестирована там (используется и API, и ботом).
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.auto_manager.schemas import (
    AiBreakerStatus,
    AutoManagerConfigData,
    AutoManagerConfigOut,
)
from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.user import User
from uk_management_bot.services.ai_manager import breaker, templates
from uk_management_bot.services.ai_manager.triage import EMERGENCY_KEYWORDS
from uk_management_bot.services.auto_manager.config import load_config, save_config
from uk_management_bot.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

router = APIRouter()
_BREAKER_CLOSED = {"open": False, "open_ttl": 0, "failures": 0}


async def _response(data: dict) -> AutoManagerConfigOut:
    """Конфиг + read-only состояние площадки: флаг ИИ, предохранитель (Redis —
    в потоке, sync-клиент с таймаутом), стандартные тексты пингов, базовые
    аварийные слова."""
    status = await asyncio.to_thread(breaker.status) if settings.AI_MANAGER_ENABLED else None
    return AutoManagerConfigOut.model_validate({
        **data,
        "ai_available": settings.AI_MANAGER_ENABLED,
        "ai_status": status,
        "template_defaults": templates.defaults(),
        "base_emergency_keywords": list(EMERGENCY_KEYWORDS),
    })


@router.get("/auto-manager-config", response_model=AutoManagerConfigOut)
async def get_auto_manager_config(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_action("auto_manager.configure")),
) -> AutoManagerConfigOut:
    """Текущий конфиг авто-менеджера. Доступен manager ИЛИ admin.

    Толерантен к отсутствующей строке/таблице (миграция не накатана) — отдаёт
    дефолт вместо падения (см. `load_config`)."""
    data = await load_config(db)
    return await _response(data)


@router.put("/auto-manager-config", response_model=AutoManagerConfigOut)
@limiter.limit("30/minute")
async def update_auto_manager_config(
    request: Request,
    payload: AutoManagerConfigData,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_action("auto_manager.configure")),
) -> AutoManagerConfigOut:
    """Сохранить конфиг авто-менеджера. Доступен manager ИЛИ admin.

    Write-side rate-limit 30/min зеркалит `board_config`'s PUT (SEC-084) —
    та же защита от churn конфига украденным токеном."""
    before = await load_config(db)
    saved = await save_config(db, payload.config_dict(), updated_by=user.id)
    logger.info("auto_manager_config обновлён пользователем %s", user.id)
    await _notify_ai_switched_off(before.get("mode", "rule"), saved.get("mode", "rule"))
    return await _response(saved)


@router.post("/auto-manager-config/ai-breaker/reset", response_model=AiBreakerStatus)
@limiter.limit("10/minute")
async def reset_ai_breaker(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_action("auto_manager.configure")),
) -> AiBreakerStatus:
    """Снять предохранитель ИИ-триажа досрочно (manager ИЛИ admin).

    Факт сброса — строка `audit_logs` (`ai_breaker_reset`: кто, когда, прежнее
    состояние). Redis недоступен — 503, ничего не записано."""
    before = await asyncio.to_thread(breaker.status)
    if before is None or not await asyncio.to_thread(breaker.reset):
        raise HTTPException(status_code=503, detail="Redis недоступен — предохранитель не сброшен")
    db.add(AuditLog(user_id=user.id, action="ai_breaker_reset",
                    details={"before": before, "at": utc_now().isoformat()}))
    await db.commit()
    logger.info("ai_manager: предохранитель сброшен пользователем %s", user.id)
    return AiBreakerStatus(**(await asyncio.to_thread(breaker.status) or _BREAKER_CLOSED))


async def _notify_ai_switched_off(old_mode: str, new_mode: str) -> None:
    """ai → rule: менеджерам — сколько открытых заявок было на SLA-эскалации.
    Счёт — короткой sync-сессией в потоке, отправка — API-sender'ом. Best-effort."""
    if old_mode != "ai" or new_mode == "ai":
        return
    import asyncio

    from uk_management_bot.api import telegram_send

    try:
        notices = await asyncio.to_thread(_collect_switch_off_notices, old_mode, new_mode)
        for tg_id, text in notices:
            await telegram_send.send_message(tg_id, text, parse_mode="HTML")
    except Exception as e:
        logger.warning("ai_manager: уведомление о выключении не отправлено: %s", type(e).__name__)


def _collect_switch_off_notices(old_mode: str, new_mode: str) -> list[tuple[int, str]]:
    """Sync-юнит для потока: своя короткая сессия, наружу — (telegram_id, text)."""
    from uk_management_bot.database.session import SessionLocal
    from uk_management_bot.services.ai_manager.switch_off import manager_notices_sync

    session = SessionLocal()
    try:
        return manager_notices_sync(session, old_mode, new_mode)
    finally:
        session.close()
