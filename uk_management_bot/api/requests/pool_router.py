"""GET /api/v2/requests/pool — вкладка «Взять» простого режима исполнителя.

Пул = ТОЛЬКО заявки с групповым назначением (решение владельца): что текущий
исполнитель может взять прямо сейчас через `POST /{n}/claim`. Правила взятия
здесь не повторяются: SQL-предфильтр в `service.claim_pool_rows`, финальное
решение — канон `workflow_runner.claimable_by_actor_async` (тот же
`allowed_actions`, что гейтит EXECUTOR_CLAIM).

Путь под уже заявленным edge-префиксом `/api/v2/requests/` — отдельный
`/api/v2/executor/...` на edge не пройдёт (там заявлен только
`/api/v2/executor/shifts/`). Роутер подключается ДО основного роутера заявок,
иначе `GET /{request_number}` перехватил бы `pool`.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.requests import service as svc
from uk_management_bot.api.requests.elevator_fields import card_language
from uk_management_bot.api.requests.schemas import PoolItem, PoolResponse
from uk_management_bot.database.models.user import User
from uk_management_bot.services.request_media_entries import parse_media_entries
from uk_management_bot.services.workflow_runner import claimable_by_actor_async
from uk_management_bot.utils.address_helpers import localize_address
from uk_management_bot.utils.request_workflow import PrincipalRef, normalize_status

router = APIRouter()

POOL_DEFAULT_LIMIT = 50
POOL_MAX_LIMIT = 100


def _first_line(text: Optional[str]) -> Optional[str]:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return None


def _photo_media_id(raw: Any) -> Optional[int]:
    return next((e.media_id for e in parse_media_entries(raw)
                 if e.kind == "photo" and e.media_id is not None), None)


def _pool_item(req, language: str) -> PoolItem:
    apartment = req.apartment_obj
    building = apartment.building if apartment is not None else req.building_obj
    return PoolItem(
        request_number=req.request_number,
        status=normalize_status(req),
        category=req.category,
        urgency=req.urgency,
        description_first_line=_first_line(req.description),
        address=localize_address(req.address, language) if req.address else None,
        address_type=req.address_type,
        building_address=building.address if building is not None else None,
        entrance=apartment.entrance if apartment is not None else None,
        floor=apartment.floor if apartment is not None else None,
        apartment_number=apartment.apartment_number if apartment is not None else None,
        photo_media_id=_photo_media_id(req.media_files),
        created_at=req.created_at,
    )


@router.get("/pool", response_model=PoolResponse)
async def get_claim_pool(
    limit: int = Query(POOL_DEFAULT_LIMIT, ge=1, le=POOL_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("executor")),
):
    """Заявки, которые исполнитель может взять сейчас: срочные первыми, затем
    по очереди (старые раньше). Не на смене → `on_shift=false`, пустой список."""
    on_shift, candidates = await svc.claim_pool_rows(
        db, user=user, limit=limit, offset=offset)
    principal = PrincipalRef(kind="user", user_id=user.id, source="api")
    claimable = await claimable_by_actor_async(db, candidates, principal)
    language = card_language(user)
    return PoolResponse(
        on_shift=on_shift,
        items=[_pool_item(r, language) for r in claimable],
    )
