from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.authz import can
from uk_management_bot.utils.auth_helpers import get_user_roles
from uk_management_bot.api.callcenter.schemas import (
    AddressOption,
    AddressSuggestBody,
    AddressSuggestOut,
    ApartmentNumberOut,
    CallCenterCapabilities,
    CallCenterCreateRequest,
    RequestCheckBody,
    RequestCheckIssue,
    RequestCheckOut,
    CallerApartmentOut,
    ResidentSearchResult,
)
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.config.settings import settings
from uk_management_bot.api.callcenter import check, service
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

# Чтения экрана приёма звонка: с ролью «Диспетчер» круг пользователей шире
# менеджеров, поэтому поиск жителей (ПДн) и справочник — под лимитом.
READ_LIMIT = "60/minute"
# Создание заявки будит диспетчеризацию и уведомления исполнителям.
CREATE_LIMIT = "30/minute"
# Поиск по номеру: меньше цифр — уже не «кто звонит», а перебор справочника.
PHONE_QUERY_MIN_DIGITS = 7


def _address_option(o: dict) -> AddressOption:
    """Вариант матчера справочника → схема ответа (двор сам себе ``yard_id``)."""
    return AddressOption(type=o["type"], id=o["id"], yard_id=o.get("yard_id", o["id"]), label=o["label_full"])


@router.get("/search-resident", response_model=list[ResidentSearchResult])
@limiter.limit(READ_LIMIT)
async def search_resident(
    request: Request,
    q: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_action("callcenter.use")),
):
    """Поиск жителя для заявки по звонку.

    По имени ищет только тот, кто и так ведёт жителей (`residents.manage`);
    остальным (диспетчер) — только по номеру телефона звонящего."""
    if not can(user, "residents.manage") and not (q.isdigit() and len(q) >= PHONE_QUERY_MIN_DIGITS):
        raise HTTPException(status_code=422, detail="search by phone digits only")
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
@limiter.limit(CREATE_LIMIT)
async def create_call_center_request(
    request: Request,
    body: CallCenterCreateRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_action("callcenter.use")),
):
    """Менеджер заводит заявку (call-центр) — от имени жителя или от себя.

    Модель доступа (план «Обходчик», адрес из справочника — 2026-11-07):
      * адрес — ровно один уровень справочника (схема: иначе 422), свободный
        текст не принимается;
      * несуществующий target user → 404; не-житель → 422;
      * квартира при выбранном жителе обязана быть ЕГО (approved+активна) →
        иначе 422; без жителя — любая активная квартира;
      * двор/дом — любой активный (роль `manager` в матрице request_address);
      * адрес в заявке всегда канонический, из справочника;
      * без user_id владелец — сам менеджер.
    """
    owner_id = user.id  # по умолчанию владелец — актор-менеджер
    level, address_id = body.address_level()
    # Квартира выбранного жителя — проверка принадлежности ЕМУ (не актору).
    resolve_as = (user.id, "manager")
    if body.user_id is not None:
        target = await service.user_by_id(db, body.user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="target user not found")
        if "applicant" not in get_user_roles(target):
            raise HTTPException(status_code=422, detail="target user is not an applicant")
        owner_id = target.id
        if level == "apartment":
            resolve_as = (target.id, "applicant")
    try:
        resolved = await resolve_request_address_async(db, *resolve_as, level, address_id)
    except AddressResolutionError as e:
        # Для call-центра «чужой/неактивный/несуществующий» адрес — некорректный
        # ввод менеджера → всегда 422 (не 403).
        raise HTTPException(status_code=422, detail=e.message)

    note_lines = []
    if body.caller_name or body.caller_phone:
        note_lines.append(f"Звонок: {body.caller_name or ''} {body.caller_phone or ''}".strip())  # html-raw: пишется в notes заявки (БД), экранируется в точке вывода
    if body.address_text and body.address_text.strip():
        # Детали для исполнителя (этаж, подъезд) — адрес заявки всё равно из справочника.
        note_lines.append(f"Адрес со слов звонящего: {body.address_text.strip()}")  # html-raw: notes (БД), экранируется при выводе
    notes = "\n".join(note_lines) or None

    try:
        persisted = await service.persist_call_center_request(
            db,
            owner_id=owner_id,
            category=body.category,
            urgency=body.urgency,
            description=body.description,
            apartment_id=resolved.apartment_id,
            building_id=resolved.building_id,
            yard_id=resolved.yard_id,
            address=resolved.canonical_address,
            address_type=resolved.address_type,
            notes=notes,
            elevator_id=body.elevator_id,
            elevator_operational=body.elevator_operational,
            acceptance_mode=body.acceptance_mode,
            # A9-P2-7: уведомление о назначении — после ответа.
            schedule_notify=background.add_task,
        )
    except ElevatorValidationError as exc:
        # Лифт не найден / архивирован / не введён — некорректный ввод менеджера → 422.
        raise elevator_http_error(exc)
    return persisted_card(persisted, language=card_language(user))


@router.get("/capabilities", response_model=CallCenterCapabilities)
async def call_center_capabilities(
    _user: User = Depends(require_action("callcenter.use")),
):
    """Что показывать в форме: свободный ввод адреса — только при включённом
    ИИ на площадке (решение владельца 2026-11-07)."""
    return CallCenterCapabilities(address_suggest=settings.AI_MANAGER_ENABLED)


@router.post("/address-suggest", response_model=AddressSuggestOut)
@limiter.limit("20/minute")
async def suggest_call_center_address(
    request: Request,
    body: AddressSuggestBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_action("callcenter.use")),
):
    """Адрес со слов звонящего → варианты двора/дома из справочника.

    Платный вызов модели — поэтому только при включённом ИИ и под лимитом.
    Варианты лишь подсказка: адрес заявки выбирает и подтверждает менеджер."""
    if not settings.AI_MANAGER_ENABLED:
        raise HTTPException(status_code=404, detail="address suggest is not enabled")
    found = await service.suggest_address(db, body.address_text, body.description)
    return AddressSuggestOut(
        options=[_address_option(o) for o in found.options],
        ai_used=found.ai_used,
        category=found.category,
        urgency=found.urgency,
    )


@router.get("/buildings/{building_id}/apartments", response_model=list[ApartmentNumberOut])
@limiter.limit(READ_LIMIT)
async def list_building_apartments(
    request: Request,
    building_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_action("callcenter.use")),
):
    """Номера квартир дома для выбора адреса. Данных жильцов нет: полный
    список квартир (`/addresses/buildings/{id}/apartments`) — за `addresses.manage`."""
    apartments = await service.list_building_apartments(db, building_id)
    if apartments is None:
        raise HTTPException(status_code=404, detail="building not found")
    return [ApartmentNumberOut(id=a.id, number=a.apartment_number) for a in apartments]


@router.get("/residents/{user_id}/apartments", response_model=list[CallerApartmentOut])
@limiter.limit(READ_LIMIT)
async def list_resident_apartments(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_action("callcenter.use")),
):
    """Квартиры найденного по телефону жителя — адрес заявки в одно касание.

    Только одобренный житель: по произвольному id нельзя узнать, где живёт
    сотрудник или неодобренный аккаунт."""
    target = await service.user_by_id(db, user_id)
    if target is None or target.status != "approved" or "applicant" not in get_user_roles(target):
        raise HTTPException(status_code=404, detail="resident not found")
    return [CallerApartmentOut(id=a["id"], label=a["label"], building_id=a["building_id"])
            for a in await service.list_resident_apartments(db, user_id)]


@router.post("/check", response_model=RequestCheckOut)
@limiter.limit("20/minute")
async def check_call_center_request(
    request: Request,
    body: RequestCheckBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_action("callcenter.use")),
):
    """Проверка заявки перед отправкой: замечания к полям — совет, не запрет.

    Платный вызов модели — только при включённом ИИ и под лимитом. Сбой модели
    даёт пустой список: приём звонка от ИИ не зависит."""
    if not settings.AI_MANAGER_ENABLED:
        raise HTTPException(status_code=404, detail="request check is not enabled")
    level, address_id = body.address_level()
    found = await check.check_request(
        db, description=body.description, category=body.category, urgency=body.urgency,
        level=level, address_id=address_id,
    )
    return RequestCheckOut(
        ai_used=found.ai_used,
        issues=[
            RequestCheckIssue(field=i.field, code=i.code, suggestion=i.suggestion,
                              options=[_address_option(o) for o in i.options])
            for i in found.issues
        ],
    )
