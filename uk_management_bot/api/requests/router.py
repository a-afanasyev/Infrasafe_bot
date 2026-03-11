from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from uk_management_bot.api.dependencies import get_db, get_current_user, require_roles, _parse_user_roles
from uk_management_bot.api.requests.schemas import (
    RequestCard, KanbanResponse, KanbanColumn,
    CreateRequestBody, UpdateRequestBody,
    CommentBody, CommentOut,
)
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_comment import RequestComment
from uk_management_bot.database.models.user import User
from uk_management_bot.services.redis_pubsub import publish_request_event

router = APIRouter()

KANBAN_STATUSES = ["Новая", "В работе", "Закуп", "Уточнение", "Выполнена", "Исполнено", "Принято", "Отменена"]


def _generate_request_number(today_str: str, count: int) -> str:
    """Generate request number. Format: YYMMDD-NNNN (supports up to 9999 per day)."""
    return f"{today_str}-{(count + 1):04d}"


@router.get("/kanban", response_model=KanbanResponse)
async def get_kanban(
    executor_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Request)
    if executor_id:
        query = query.filter(Request.executor_id == executor_id)
    if category:
        query = query.filter(Request.category == category)

    result = await db.execute(query.order_by(Request.created_at.desc()).limit(500))
    requests = result.scalars().all()

    columns = []
    for st in KANBAN_STATUSES:
        st_requests = [r for r in requests if r.status == st]
        columns.append(KanbanColumn(
            status=st,
            count=len(st_requests),
            requests=[RequestCard.model_validate(r) for r in st_requests],
        ))
    return KanbanResponse(columns=columns)


@router.get("", response_model=list[RequestCard])
async def list_requests(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    executor_id: Optional[int] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Request)
    if status:
        query = query.filter(Request.status == status)
    if category:
        query = query.filter(Request.category == category)
    if executor_id:
        query = query.filter(Request.executor_id == executor_id)
    if source:
        query = query.filter(Request.source == source)

    result = await db.execute(query.order_by(Request.created_at.desc()).offset(offset).limit(limit))
    return [RequestCard.model_validate(r) for r in result.scalars().all()]


@router.get("/{request_number}", response_model=RequestCard)
async def get_request(
    request_number: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Request).where(Request.request_number == request_number))
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    return RequestCard.model_validate(req)


@router.post("", response_model=RequestCard, status_code=201)
async def create_request(
    body: CreateRequestBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    today = date.today().strftime("%y%m%d")
    count_result = await db.execute(
        select(func.count(Request.request_number)).where(
            Request.request_number.like(f"{today}-%")
        )
    )
    count = count_result.scalar() or 0
    request_number = _generate_request_number(today, count)

    req = Request(
        request_number=request_number,
        user_id=user.id,
        category=body.category,
        urgency=body.urgency,
        description=body.description,
        apartment_id=body.apartment_id,
        address=body.address,
        status="Новая",
        source=body.source,
        media_files=body.media_files or [],
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)

    await publish_request_event("request.created", RequestCard.model_validate(req).model_dump(mode="json"))
    return RequestCard.model_validate(req)


@router.patch("/{request_number}", response_model=RequestCard)
async def update_request(
    request_number: str,
    body: UpdateRequestBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    result = await db.execute(select(Request).where(Request.request_number == request_number))
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    old_status = req.status
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(req, field, value)

    await db.commit()
    await db.refresh(req)

    if old_status != req.status:
        event_data = {"number": request_number, "old_status": old_status, "new_status": req.status}
        await publish_request_event("request.status_changed", event_data)

    return RequestCard.model_validate(req)


@router.get("/{request_number}/comments", response_model=list[CommentOut])
async def get_comments(
    request_number: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify request exists
    req_result = await db.execute(select(Request).where(Request.request_number == request_number))
    if not req_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Request not found")

    user_roles = _parse_user_roles(user)
    is_manager = any(r in user_roles for r in ["manager", "admin"])

    query = select(RequestComment).where(RequestComment.request_number == request_number)
    if not is_manager:
        query = query.where(RequestComment.is_internal == False)  # noqa: E712

    result = await db.execute(query.order_by(RequestComment.created_at.asc()))
    return result.scalars().all()


@router.post("/{request_number}/comments", response_model=CommentOut, status_code=201)
async def add_comment(
    request_number: str,
    body: CommentBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Only managers can create internal comments
    if body.is_internal:
        user_roles = _parse_user_roles(user)
        if not any(r in user_roles for r in ["manager", "admin"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only managers can create internal comments")

    comment = RequestComment(
        request_number=request_number,
        user_id=user.id,
        comment_type="clarification",
        comment_text=body.text,
        is_internal=body.is_internal,
        media_files=body.media_files or [],
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment
