from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_roles, _parse_user_roles
from uk_management_bot.api.callcenter.schemas import ResidentSearchResult, CallCenterCreateRequest
from uk_management_bot.api.callcenter import service
from uk_management_bot.api.elevators.errors import http_error as elevator_http_error
from uk_management_bot.api.requests.elevator_fields import card_language, persisted_card
from uk_management_bot.api.requests.schemas import RequestCard
from uk_management_bot.services.elevator_service import ElevatorValidationError
from uk_management_bot.services.request_address import (
    resolve_request_address_async,
    AddressResolutionError,
)
from uk_management_bot.database.models.user import User

router = APIRouter()


@router.get("/search-resident", response_model=list[ResidentSearchResult])
async def search_resident(
    q: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    rows = await service.search_approved_applicants(db, q=q)
    return [
        ResidentSearchResult(
            id=row.id,
            telegram_id=row.telegram_id,
            full_name=" ".join(filter(None, [row.first_name, row.last_name])),
            phone=row.phone,
            address=None,
            requests_count=row.requests_count or 0,
        )
        for row in rows
    ]


@router.post("/requests", response_model=RequestCard, status_code=201)
async def create_call_center_request(
    body: CallCenterCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    """Менеджер заводит заявку (call-центр) — от имени жителя или от себя.

    Модель доступа (план «Обходчик»):
      * apartment_id без user_id → 422;
      * несуществующий target user → 404; не-житель → 422;
      * квартира должна принадлежать именно target user (approved+активна) → иначе
        422 (resolver-ветка проверяет принадлежность к target user_id, не к актору);
      * при выбранной квартире клиентский address игнорируется → канонический;
      * building_id (T6, ремонт лифта из карточки) → любой активный дом (роль
        `manager` в матрице request_address, building-only), address_type=
        'building', клиентский address игнорируется; вместе с apartment_id → 422
        (схема);
      * без квартиры/дома свободный address обязателен и непустой →
        address_type='legacy';
      * без user_id владелец — сам менеджер.
    """
    # apartment_id без выбранного жителя — некому принадлежать.
    if body.apartment_id is not None and body.user_id is None:
        raise HTTPException(status_code=422, detail="apartment_id requires user_id")

    owner_id = user.id  # по умолчанию владелец — актор-менеджер
    resolved = None
    if body.user_id is not None:
        target = await service.user_by_id(db, body.user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="target user not found")
        if "applicant" not in _parse_user_roles(target):
            raise HTTPException(status_code=422, detail="target user is not an applicant")
        owner_id = target.id
        if body.apartment_id is not None:
            try:
                # Принадлежность к TARGET user_id (не к менеджеру-актору).
                resolved = await resolve_request_address_async(
                    db, target.id, "applicant", "apartment", body.apartment_id
                )
            except AddressResolutionError as e:
                # Для call-центра «чужая/неактивная/несуществующая» квартира —
                # некорректный ввод менеджера → всегда 422 (не 403).
                raise HTTPException(status_code=422, detail=e.message)

    if body.building_id is not None:
        try:
            # Уровень дома: любой активный дом, принадлежность не требуется.
            resolved = await resolve_request_address_async(
                db, user.id, "manager", "building", body.building_id
            )
        except AddressResolutionError as e:
            raise HTTPException(status_code=422, detail=e.message)

    if resolved is not None:
        # Резолвер отдаёт ровно один FK + уровень — согласовано с CHECK модели.
        address = resolved.canonical_address
        apartment_id = resolved.apartment_id
        building_id = resolved.building_id
        address_type = resolved.address_type
    else:
        # Без квартиры/дома — свободный адрес обязателен и непуст → legacy.
        if not body.address or not body.address.strip():
            raise HTTPException(status_code=422, detail="address required when no apartment")
        address = body.address.strip()
        apartment_id = None
        building_id = None
        address_type = "legacy"

    notes = None
    if body.caller_name or body.caller_phone:
        notes = f"Звонок: {body.caller_name or ''} {body.caller_phone or ''}".strip()

    try:
        persisted = await service.persist_call_center_request(
            db,
            owner_id=owner_id,
            category=body.category,
            urgency=body.urgency,
            description=body.description,
            apartment_id=apartment_id,
            building_id=building_id,
            address=address,
            address_type=address_type,
            notes=notes,
            elevator_id=body.elevator_id,
            elevator_operational=body.elevator_operational,
            acceptance_mode=body.acceptance_mode,
        )
    except ElevatorValidationError as exc:
        # Лифт не найден / архивирован / не введён — некорректный ввод менеджера → 422.
        raise elevator_http_error(exc)
    return persisted_card(persisted, language=card_language(user))
