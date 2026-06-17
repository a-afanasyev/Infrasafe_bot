from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func

from uk_management_bot.api.dependencies import get_db, require_roles, _parse_user_roles
from uk_management_bot.api.callcenter.schemas import ResidentSearchResult, CallCenterCreateRequest
from uk_management_bot.api.requests.schemas import RequestCard
from uk_management_bot.services.request_number_service import RequestNumberService
from uk_management_bot.services.request_address import (
    resolve_request_address_async,
    AddressResolutionError,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.request import Request

router = APIRouter()


def _escape_like(s: str) -> str:
    """Escape LIKE wildcards in user input."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/search-resident", response_model=list[ResidentSearchResult])
async def search_resident(
    q: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    escaped_q = _escape_like(q)
    pattern = f"%{escaped_q}%"

    # Single query with subquery for request count to avoid N+1
    count_subq = (
        select(func.count(Request.request_number))
        .where(Request.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )

    result = await db.execute(
        select(
            User.id,
            User.telegram_id,
            User.first_name,
            User.last_name,
            User.phone,
            count_subq.label("requests_count"),
        ).where(
            # Только approved-жители: менеджер не должен выбрать того, кому потом
            # нельзя создать заявку (план «Обходчик», R52).
            User.status == "approved",
            or_(
                User.roles.like('%"applicant"%'),
                User.role == "applicant",
            ),
            or_(
                User.phone.ilike(pattern),
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
            )
        ).limit(10)
    )
    rows = result.all()
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
      * без квартиры свободный address обязателен и непустой → address_type='legacy';
      * без user_id владелец — сам менеджер (legacy-адрес).
    """
    # apartment_id без выбранного жителя — некому принадлежать.
    if body.apartment_id is not None and body.user_id is None:
        raise HTTPException(status_code=422, detail="apartment_id requires user_id")

    owner_id = user.id  # по умолчанию владелец — актор-менеджер
    resolved = None
    if body.user_id is not None:
        target = await db.get(User, body.user_id)
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

    if resolved is not None:
        address = resolved.canonical_address
        apartment_id = resolved.apartment_id
        address_type = "apartment"
    else:
        # Без квартиры — свободный адрес обязателен и непуст → legacy.
        if not body.address or not body.address.strip():
            raise HTTPException(status_code=422, detail="address required when no apartment")
        address = body.address.strip()
        apartment_id = None
        address_type = "legacy"

    # PR5: атомарный счётчик дня (раньше COUNT(*)+1 без retry — коллизия
    # после удаления строки роняла запрос 500-кой).
    request_number = await RequestNumberService.next_number_async(db)

    notes = None
    if body.caller_name or body.caller_phone:
        notes = f"Звонок: {body.caller_name or ''} {body.caller_phone or ''}".strip()

    req = Request(
        request_number=request_number,
        user_id=owner_id,
        category=body.category,
        urgency=body.urgency,
        description=body.description,
        apartment_id=apartment_id,
        address=address,
        address_type=address_type,
        status="Новая",
        source="call_center",
        notes=notes,
        media_files=[],
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)

    # FEAT-группы (followup #1): call-center — ещё один канал создания. Авто-dispatch
    # на группу-специализацию (Новая→В работе + group) через канонический
    # run_command, как в _persist_request (twa/inspector) и боте. Best-effort —
    # ошибка не валит уже-созданную заявку. refresh — чтобы карточка отразила статус.
    from uk_management_bot.services.dispatch import auto_dispatch_new_request_async
    await auto_dispatch_new_request_async(req.request_number, body.category)
    await db.refresh(req)
    return RequestCard.model_validate(req)
