from datetime import date
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_approved_roles
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.user import User

router = APIRouter()
staff = require_approved_roles("manager", "admin")
MAX_BYTES = 5 * 1024 * 1024


async def service_request(method, path, user, **kwargs):
    if not settings.PAYMENT_SERVICE_TOKEN:
        raise HTTPException(503, "Сервис контроля платежей не настроен")
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.request(method, f"{settings.PAYMENT_SERVICE_URL.rstrip('/')}{path}",
                                            headers={"X-Service-Token": settings.PAYMENT_SERVICE_TOKEN,
                                                     "X-Actor-Id": str(user.id)}, **kwargs)
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Сервис контроля платежей недоступен") from exc
    if response.status_code in (400, 404, 409, 422):
        try:
            detail = response.json().get("detail", "Ошибка проверки данных")
        except ValueError:
            detail = "Ошибка проверки данных"
        raise HTTPException(response.status_code, detail)
    if not response.is_success:
        raise HTTPException(503, "Сервис контроля платежей недоступен")
    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(502, "Некорректный ответ сервиса контроля платежей") from exc


@router.get("/apartments/{apartment_id}")
async def apartment_balance(apartment_id: int, user: User = Depends(staff), db: AsyncSession = Depends(get_db)):
    apartment = await db.get(Apartment, apartment_id)
    if apartment is None:
        raise HTTPException(404, "Apartment not found")
    number = apartment.account_number
    result = {"account_number": number, "status": "no_account", "current": None}
    if not number:
        return result
    try:
        data = await service_request("GET", "/account", user, params={"account_number": number})
        return {**result, "status": data["status"], "current": data["current"]}
    except HTTPException as exc:
        if exc.status_code not in (502, 503):
            raise
        return {**result, "status": "unavailable"}


@router.get("/account")
async def account(account_number: str = Query(..., min_length=1, max_length=64), user: User = Depends(staff)):
    return await service_request("GET", "/account", user, params={"account_number": account_number})


@router.get("/imports")
async def imports(offset: int = Query(0, ge=0), user: User = Depends(staff)):
    return await service_request("GET", "/imports", user, params={"offset": offset})


@router.post("/imports/preview")
@limiter.limit("10/minute")
async def preview(request: Request, kind: Literal["balances", "payments"] = Form(...),
                  as_of: date = Form(...), source: str = Form(..., min_length=1, max_length=100),
                  file: UploadFile = File(...), user: User = Depends(staff)):
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "Файл превышает 5 МБ")
    return await service_request("POST", "/imports/preview", user,
                                 data={"kind": kind, "as_of": as_of.isoformat(), "source": source},
                                 files={"file": (file.filename or "upload", content, file.content_type)})


@router.get("/imports/{batch_id}")
async def import_detail(batch_id: int, offset: int = Query(0, ge=0), user: User = Depends(staff)):
    return await service_request("GET", f"/imports/{batch_id}", user, params={"offset": offset})


@router.post("/imports/{batch_id}/activate")
@limiter.limit("30/minute")
async def activate(request: Request, batch_id: int, user: User = Depends(staff)):
    return await service_request("POST", f"/imports/{batch_id}/activate", user)


class Deactivate(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/imports/{batch_id}/deactivate")
@limiter.limit("30/minute")
async def deactivate(request: Request, batch_id: int, body: Deactivate, user: User = Depends(staff)):
    return await service_request("POST", f"/imports/{batch_id}/deactivate", user, json=body.model_dump())
