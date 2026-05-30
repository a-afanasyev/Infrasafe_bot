from __future__ import annotations
import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.api.auth.service import verify_twa_init_data
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.api.registration.tickets import (
    create_registration_ticket, verify_registration_ticket,
)
from uk_management_bot.api.registration.catalog import list_apartments, is_apartment_selectable, get_apartment_label
from uk_management_bot.api.registration.schemas import (
    StartIn, StartOut, Prefill, RegisterApplicantIn, RegistrationResult,
)
from uk_management_bot.api.registration.notify import notify_managers_new_registration
from uk_management_bot.services.addresses import core as address_core
from uk_management_bot.services.addresses.exceptions import (
    AddressConflict, AddressNotFound, AddressValidationError,
)
from uk_management_bot.utils.validators import Validator
from uk_management_bot.utils.auth_helpers import parse_roles_safe

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


def _ticket_telegram_id(authorization: str | None) -> int:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing registration ticket")
    tid = verify_registration_ticket(authorization.split(" ", 1)[1])
    if tid is None:
        raise HTTPException(status_code=401, detail="Invalid or expired registration ticket")
    return tid


@router.post("/applicant", response_model=RegistrationResult)
@limiter.limit("3/minute")
async def register_applicant(
    request: Request,
    body: RegisterApplicantIn,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    telegram_id = _ticket_telegram_id(authorization)

    ok, msg = Validator.validate_phone(body.phone)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    phone = body.phone.strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    full_name = body.full_name.strip()
    if not full_name:
        raise HTTPException(status_code=400, detail="ФИО обязательно")

    if not await is_apartment_selectable(db, body.apartment_id):
        raise HTTPException(status_code=400, detail="Квартира недоступна для выбора")

    def _apply_applicant_fields(u: User) -> None:
        u.first_name = full_name.split()[0]
        u.last_name = " ".join(full_name.split()[1:])
        u.phone = phone
        u.active_role = "applicant"
        r = set(parse_roles_safe(u.roles)); r.add("applicant")
        u.roles = json.dumps(sorted(r))

    user = (await db.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
    if user and user.status == "blocked":
        raise HTTPException(status_code=403, detail="Пользователь заблокирован")
    if user and user.status == "approved":
        raise HTTPException(status_code=409, detail="Уже зарегистрирован")
    if user is None:
        user = User(telegram_id=telegram_id, status="pending")
        db.add(user)
    _apply_applicant_fields(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        user = (await db.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one()
        if user.status == "blocked":
            raise HTTPException(status_code=403, detail="Пользователь заблокирован")
        if user.status == "approved":
            raise HTTPException(status_code=409, detail="Уже зарегистрирован")
        _apply_applicant_fields(user)
        await db.flush()

    existing_ua = (await db.execute(select(UserApartment).where(
        UserApartment.user_id == user.id,
        UserApartment.apartment_id == body.apartment_id,
    ))).scalar_one_or_none()
    if existing_ua is not None:
        if existing_ua.status == "pending":
            await db.commit()
            return RegistrationResult(status="pending")
        if existing_ua.status == "approved":
            await db.rollback()
            raise HTTPException(status_code=409, detail="Вы уже подтверждены как житель этой квартиры")
        await db.rollback()
        raise HTTPException(status_code=409, detail="Предыдущая заявка отклонена. Обратитесь к администратору.")

    try:
        await address_core.request_apartment(db, user_id=user.id, apartment_id=body.apartment_id)
    except AddressConflict as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except (AddressNotFound, AddressValidationError) as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except IntegrityError:
        await db.rollback()
        return RegistrationResult(status="pending")

    label = await get_apartment_label(db, body.apartment_id)
    await notify_managers_new_registration(
        telegram_id=telegram_id, full_name=full_name, apartment_label=label,
    )
    return RegistrationResult(status="pending")
