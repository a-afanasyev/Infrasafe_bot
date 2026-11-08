"""Привязка адреса из справочника к заявке без него (решение владельца 2026-11-07).

Заявка с legacy-текстом адреса («4g 10 etaj») не уходит в работу —
`plan_transition` отказывает в назначении. Менеджер выбирает двор, дом или
квартиру, и заявка становится обычной: её можно назначить, она попадает в
отчёты о работах.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.api.requests import service as svc
from uk_management_bot.api.requests.router import _card
from uk_management_bot.api.requests.schemas import BindAddressBody, RequestCard
from uk_management_bot.database.models.user import User
from uk_management_bot.services.redis_pubsub import publish_request_event
from uk_management_bot.services.request_address import (
    AddressResolutionError,
    resolve_request_address_async,
)

router = APIRouter()


@router.patch("/{request_number}/address", response_model=RequestCard)
@limiter.limit("30/minute")
async def bind_request_address(
    request: Request,
    request_number: str,
    body: BindAddressBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_action("requests.manage")),
):
    """Двор/дом/квартира из справочника — к заявке с legacy-адресом.

    404 — нет заявки; 409 — адрес уже из справочника (перепривязку не делаем:
    это другой вопрос с последствиями для группы и отчётов); 422 — адрес
    неактивен/не существует."""
    level, address_id = body.address_level()
    try:
        resolved = await resolve_request_address_async(db, user.id, "manager", level, address_id)
    except AddressResolutionError as e:
        raise HTTPException(status_code=422, detail=e.message)
    try:
        found = await svc.bind_address(db, request_number, resolved, user.id)
    except svc.AddressAlreadyBound:
        raise HTTPException(status_code=409, detail="address already bound to directory")
    if not found:
        raise HTTPException(status_code=404, detail="Request not found")

    await publish_request_event("request.updated", {"number": request_number})
    row = await svc.request_with_executor(db, request_number)
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")
    req, exec_user = row
    return await _card(db, req, exec_user, user)
