"""Выпуск одноразового launch-ticket для внешнего «Учёт ресурсов УК».

Дашборд встраивает `resources.infrasafe.uz` в iframe (и умеет открывать его в
отдельной вкладке). Чтобы авторизовать пользователя без повторного логина, наш
backend выпускает одноразовый opaque launch-ticket: server-to-server POST к
партнёрскому API с сервисным токеном (`X-Service-Token`). Токен живёт ТОЛЬКО на
бэкенде и НИКОГДА не уходит в браузер — клиент получает лишь `ticket` + TTL.

Роль для партнёра выводится на бэке из ролей пользователя (authoritative) —
данным клиента не доверяем.
"""
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.auth.service import verify_twa_init_data
from uk_management_bot.api.dependencies import _parse_user_roles, get_db, require_roles
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.api.users.queries import get_user_by_telegram_id
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

_TIMEOUT = 10.0

# Роль-капабилити «полевой контролёр»: только ввод показаний (у партнёра —
# resource_meter_entry). Хранится строкой в user.roles, выдаётся менеджером.
METER_ENTRY_ROLE = "resource_meter_entry"


class TicketOut(BaseModel):
    ticket: str
    expires_in: int


class TwaTicketIn(BaseModel):
    init_data: str


async def _mint_resource_ticket(external_user_id: str, display_name: str, role: str) -> TicketOut:
    """Server-to-server выпуск одноразового launch-ticket у партнёра.

    Токен `X-Service-Token` живёт ТОЛЬКО на бэкенде. Fail-closed: пустой токен →
    503 (интеграция не сконфигурирована). Ошибки партнёра → 502/504.
    """
    token = settings.RESOURCE_SERVICE_TOKEN
    if not token:
        logger.warning("RESOURCE_SERVICE_TOKEN не задан — ticket-эндпоинт отключён (503)")
        raise HTTPException(status_code=503, detail="Resource accounting is not configured")

    payload = {
        "external_user_id": external_user_id,
        "display_name": display_name,
        "role": role,
    }
    url = f"{settings.RESOURCE_SERVICE_URL.rstrip('/')}/auth/tickets"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, headers={"X-Service-Token": token}, json=payload)
    except httpx.TimeoutException:
        logger.warning("resource-accounting: таймаут выпуска ticket")
        raise HTTPException(status_code=504, detail="Resource service timeout")
    except httpx.HTTPError as e:
        logger.warning("resource-accounting: сетевая ошибка выпуска ticket: %s", e)
        raise HTTPException(status_code=502, detail="Resource service unavailable")

    if resp.status_code // 100 != 2:
        logger.warning("resource-accounting: партнёр вернул HTTP %s", resp.status_code)
        raise HTTPException(status_code=502, detail="Resource service error")

    data = (resp.json() or {}).get("data") or {}
    ticket = data.get("ticket")
    if not ticket:
        logger.warning("resource-accounting: в ответе партнёра нет ticket")
        raise HTTPException(status_code=502, detail="Resource service returned no ticket")

    return TicketOut(ticket=str(ticket), expires_in=int(data.get("expires_in", 60)))


def _resource_role(user: User) -> str:
    """UK-роли → роль партнёра (authoritative, на бэке).

    system_admin/admin → resource_admin; иначе (гейт пропустил только
    manager-уровень) → resource_operator. reviewer/viewer пока не выдаём.
    """
    roles = _parse_user_roles(user)
    if "system_admin" in roles or "admin" in roles:
        return "resource_admin"
    return "resource_operator"


def _display_name(user: User) -> str:
    """Имя для отображения у партнёра (first/last nullable → безопасный fallback)."""
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return name or user.username or f"user-{user.id}"


@router.post("/ticket", response_model=TicketOut)
@limiter.limit("30/minute")
async def issue_ticket(
    request: Request,
    user: User = Depends(require_roles("manager", "system_admin", "admin")),
) -> TicketOut:
    """Одноразовый launch-ticket для встраиваемого раздела ресурсов (дашборд)."""
    return await _mint_resource_ticket(str(user.id), _display_name(user), _resource_role(user))


@router.post("/twa-ticket", response_model=TicketOut)
@limiter.limit("30/minute")
async def issue_twa_ticket(
    request: Request,
    body: TwaTicketIn,
    db: AsyncSession = Depends(get_db),
) -> TicketOut:
    """Launch-ticket контролёру из Telegram Mini App (по initData, без UK-JWT).

    Авторизация — Telegram `initData` (bot-token'ом УК), а не access-токеном:
    контролёр открывает Mini App, показания вносит в ресурс-сервис (у которого
    bot-token'а нет). Роль партнёра фиксирована `resource_meter_entry`; доступ —
    по наличию этой роли-капабилити у пользователя (менеджер выдаёт).
    """
    user_data = verify_twa_init_data(body.init_data, settings.BOT_TOKEN)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid initData")

    telegram_id = user_data.get("id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="No telegram id in initData")

    user = await get_user_by_telegram_id(db, int(telegram_id))
    if not user or user.status != "approved":
        raise HTTPException(status_code=403, detail="User not approved")

    if METER_ENTRY_ROLE not in _parse_user_roles(user):
        raise HTTPException(status_code=403, detail="Not a meter-entry controller")

    return await _mint_resource_ticket(str(user.id), _display_name(user), METER_ENTRY_ROLE)
