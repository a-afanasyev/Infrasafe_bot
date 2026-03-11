from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.callcenter.schemas import ResidentSearchResult, CallCenterCreateRequest
from uk_management_bot.api.requests.schemas import RequestCard
from uk_management_bot.api.requests.router import _generate_request_number
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
    today = date.today().strftime("%y%m%d")
    count_result = await db.execute(
        select(func.count(Request.request_number)).where(
            Request.request_number.like(f"{today}-%")
        )
    )
    count = count_result.scalar() or 0
    request_number = _generate_request_number(today, count)

    notes = None
    if body.caller_name or body.caller_phone:
        notes = f"Звонок: {body.caller_name or ''} {body.caller_phone or ''}".strip()

    req = Request(
        request_number=request_number,
        user_id=body.user_id or user.id,
        category=body.category,
        urgency=body.urgency,
        description=body.description,
        apartment_id=body.apartment_id,
        address=body.address,
        status="Новая",
        source="call_center",
        notes=notes,
        media_files=[],
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return RequestCard.model_validate(req)
