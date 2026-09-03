from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db
from uk_management_bot.api.registration import service
from uk_management_bot.api.users.queries import get_user_by_telegram_id
from uk_management_bot.api.rate_limit import limiter, auth_ratelimit_guard
from uk_management_bot.api.auth.service import verify_twa_init_data
from uk_management_bot.config.settings import settings
from uk_management_bot.api.registration.tickets import (
    create_registration_ticket, verify_registration_ticket,
)
from uk_management_bot.api.registration.catalog import (
    get_apartment_label,
    is_apartment_selectable,
    list_apartments_out,
    list_buildings_out,
    list_yards_out,
)
from uk_management_bot.api.registration.schemas import (
    StartIn, StartOut, Prefill, RegisterApplicantIn, RegistrationResult,
    RegistrationYardOut,
    RegistrationBuildingOut,
    ApartmentOut,
    ContactStatusOut,
)
from uk_management_bot.api.registration.notify import notify_managers_new_registration
from uk_management_bot.services.addresses import core as address_core
from uk_management_bot.services.addresses.exceptions import (
    AddressConflict, AddressNotFound, AddressValidationError,
)

logger = logging.getLogger(__name__)
# SEC-04: self-registration is a brute-force surface (ticket guessing, spam
# account creation) — fail-closed when the rate-limit backend is degraded.
router = APIRouter(dependencies=[Depends(auth_ratelimit_guard)])


def _resolve_telegram_id(init_data: str) -> tuple[int, dict]:
    data = verify_twa_init_data(init_data, settings.BOT_TOKEN)
    if not data or not data.get("id"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid initData")
    return int(data["id"]), data


@router.post("/start", response_model=StartOut)
@limiter.limit("10/minute")
async def start(request: Request, body: StartIn, db: AsyncSession = Depends(get_db)):
    telegram_id, tg = _resolve_telegram_id(body.init_data)

    existing = await get_user_by_telegram_id(db, telegram_id)
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
    )


def registration_ticket_telegram_id(authorization: str | None = Header(default=None)) -> int:
    """Зависимость: telegram_id из Bearer-тикета регистрации (спека §4.1)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing registration ticket")
    tid = verify_registration_ticket(authorization.split(" ", 1)[1])
    if tid is None:
        raise HTTPException(status_code=401, detail="Invalid or expired registration ticket")
    return tid


# ─── Каскад адресов и статус контакта под тикетом (спека §4.3) ───────────────

@router.get("/contact-status", response_model=ContactStatusOut)
@limiter.limit("60/minute")
async def contact_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
    telegram_id: int = Depends(registration_ticket_telegram_id),
):
    """TWA опрашивает после requestContact: контакт Telegram шлёт боту, бот
    пишет users.phone — здесь он и появляется."""
    existing = await get_user_by_telegram_id(db, telegram_id)
    return ContactStatusOut(phone=existing.phone if existing else None)


@router.get("/yards", response_model=list[RegistrationYardOut])
@limiter.limit("60/minute")
async def yards(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _telegram_id: int = Depends(registration_ticket_telegram_id),
):
    return await list_yards_out(db)


@router.get("/yards/{yard_id}/buildings", response_model=list[RegistrationBuildingOut])
@limiter.limit("60/minute")
async def yard_buildings(
    request: Request,
    yard_id: int,
    db: AsyncSession = Depends(get_db),
    _telegram_id: int = Depends(registration_ticket_telegram_id),
):
    rows = await list_buildings_out(db, yard_id)
    if rows is None:
        raise HTTPException(status_code=404, detail="Двор не найден")
    return rows


@router.get("/buildings/{building_id}/apartments", response_model=list[ApartmentOut])
@limiter.limit("60/minute")
async def building_apartments(
    request: Request,
    building_id: int,
    db: AsyncSession = Depends(get_db),
    _telegram_id: int = Depends(registration_ticket_telegram_id),
):
    rows = await list_apartments_out(db, building_id)
    if rows is None:
        raise HTTPException(status_code=404, detail="Дом не найден")
    return rows


@router.post("/applicant", response_model=RegistrationResult)
@limiter.limit("3/minute")
async def register_applicant(
    request: Request,
    body: RegisterApplicantIn,
    db: AsyncSession = Depends(get_db),
    telegram_id: int = Depends(registration_ticket_telegram_id),
):
    full_name = body.full_name.strip()
    if not full_name:
        raise HTTPException(status_code=400, detail="ФИО обязательно")

    # Телефон только из Telegram-контакта, сохранённого ботом (спека §4.4).
    # Порядок: blocked 403 → approved 409 → нет телефона 409 → квартира 400.
    existing = await get_user_by_telegram_id(db, telegram_id)
    if existing and existing.status == "blocked":
        raise HTTPException(status_code=403, detail="Пользователь заблокирован")
    if existing and existing.status == "approved":
        raise HTTPException(status_code=409, detail="Уже зарегистрирован")
    phone = existing.phone if existing else None
    if not phone:
        raise HTTPException(
            status_code=409, detail="Сначала поделитесь контактом в Telegram"
        )

    if not await is_apartment_selectable(db, body.apartment_id):
        raise HTTPException(status_code=400, detail="Квартира недоступна для выбора")

    # SEC-06 и IntegrityError-ретрай — в service.upsert_pending_applicant;
    # маппинг типизированных исходов на HTTP-коды — здесь.
    outcome, user = await service.upsert_pending_applicant(
        db,
        telegram_id=telegram_id,
        first_name=full_name.split()[0],
        last_name=" ".join(full_name.split()[1:]),
        phone=phone,
    )
    if outcome == service.UPSERT_BLOCKED:
        raise HTTPException(status_code=403, detail="Пользователь заблокирован")
    if outcome == service.UPSERT_APPROVED:
        raise HTTPException(status_code=409, detail="Уже зарегистрирован")
    if outcome == service.UPSERT_PRIVILEGED:
        raise HTTPException(
            status_code=403,
            detail="Аккаунт уже имеет роль в системе — обратитесь к менеджеру",
        )

    existing_ua = await service.apartment_link_of(
        db, user_id=user.id, apartment_id=body.apartment_id
    )
    if existing_ua is not None:
        if existing_ua.status == "pending":
            await service.commit_registration(db)
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
