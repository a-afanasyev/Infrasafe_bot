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

from uk_management_bot.api.dependencies import _parse_user_roles, require_roles
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

_TIMEOUT = 10.0


class TicketOut(BaseModel):
    ticket: str
    expires_in: int


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
    """Одноразовый launch-ticket для встраиваемого раздела ресурсов."""
    token = settings.RESOURCE_SERVICE_TOKEN
    if not token:
        # Fail-closed: интеграция не сконфигурирована — партнёра не зовём.
        logger.warning("RESOURCE_SERVICE_TOKEN не задан — ticket-эндпоинт отключён (503)")
        raise HTTPException(status_code=503, detail="Resource accounting is not configured")

    payload = {
        "external_user_id": str(user.id),
        "display_name": _display_name(user),
        "role": _resource_role(user),
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
