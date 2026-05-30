from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.api.auth.service import verify_twa_init_data
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.user import User
from uk_management_bot.api.registration.tickets import create_registration_ticket
from uk_management_bot.api.registration.catalog import list_apartments
from uk_management_bot.api.registration.schemas import StartIn, StartOut, Prefill

logger = logging.getLogger(__name__)
router = APIRouter()


def _resolve_telegram_id(init_data: str) -> tuple[int, dict]:
    data = verify_twa_init_data(init_data, settings.BOT_TOKEN)
    if not data or not data.get("id"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid initData")
    return int(data["id"]), data


@router.post("/start", response_model=StartOut)
@limiter.limit("10/minute")
async def start(request: Request, body: StartIn, db: AsyncSession = Depends(get_db)):
    telegram_id, tg = _resolve_telegram_id(body.init_data)

    existing = (await db.execute(
        select(User).where(User.telegram_id == telegram_id)
    )).scalar_one_or_none()
    if existing and existing.status == "blocked":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь заблокирован")
    if existing and existing.status == "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Уже зарегистрирован")

    prefill = Prefill(
        first_name=tg.get("first_name"),
        last_name=tg.get("last_name"),
        phone=existing.phone if existing else None,
    )
    return StartOut(
        registration_ticket=create_registration_ticket(telegram_id),
        prefill=prefill,
        apartments=await list_apartments(db),
    )
