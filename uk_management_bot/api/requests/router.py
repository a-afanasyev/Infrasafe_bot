from typing import Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from uk_management_bot.api.dependencies import get_db, get_current_user, require_roles, _parse_user_roles
from uk_management_bot.api.dependencies_access import check_request_access, require_active_shift, is_assigned_executor
from uk_management_bot.services.webhook_payloads import (
    emit_request_created,
    emit_request_status_changed,
)
from uk_management_bot.api.requests.schemas import (
    RequestCard, KanbanResponse, KanbanColumn,
    CreateRequestBody, UpdateRequestBody,
    CommentBody, CommentOut,
)
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.request_comment import RequestComment
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.webhook_inbox import WebhookInbox
from uk_management_bot.services.redis_pubsub import publish_request_event
from uk_management_bot.api.rate_limit import limiter

router = APIRouter()

KANBAN_STATUSES = ["Новая", "В работе", "Закуп", "Уточнение", "Выполнена", "Исполнено", "Принято", "Отменена"]

_REQUEST_VALID_TRANSITIONS: dict[str, set[str]] = {
    "Новая":     {"В работе", "Закуп", "Уточнение", "Отменена"},
    "В работе":  {"Закуп", "Уточнение", "Выполнена", "Отменена"},
    "Закуп":     {"В работе", "Уточнение", "Отменена"},
    "Уточнение": {"В работе", "Отменена"},
    "Выполнена": {"Исполнено", "В работе"},
    "Исполнено": {"Принято", "В работе"},
    "Принято":   set(),
    "Отменена":  set(),
}


def _generate_request_number(today_str: str, count: int) -> str:
    """Generate request number. Format: YYMMDD-NNN (supports up to 999 per day)."""
    return f"{today_str}-{(count + 1):03d}"


def _format_executor_name(user) -> Optional[str]:
    """Format executor's display name from User ORM object."""
    if user is None:
        return None
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return name or None


def _make_request_card(req, exec_user=None, inbox_row=None) -> RequestCard:
    """Build RequestCard from ORM Request, optionally with executor user.

    When `inbox_row` (a WebhookInbox row associated with this request) is
    provided, surface the Sprint 10 reopen-meta fields on the card.
    Sequence=1 (deployed-wire first-time default) → None — only true reopens
    (≥ 2) carry visible meta. List endpoints skip the enrichment to keep
    their query cost identical to pre-INT-120 baseline.
    """
    card = RequestCard.model_validate(req)
    card.executor_name = _format_executor_name(exec_user)
    if inbox_row is not None:
        alert = (inbox_row.payload or {}).get("alert", {}) or {}
        seq = alert.get("reopen_sequence")
        if isinstance(seq, int) and seq >= 2:
            card.reopen_sequence = seq
            card.reopen_chain_id = alert.get("reopen_chain_id") or None
            card.related_request_number = alert.get("related_request_number") or None
        # engineer_required_reason is independent of the seq≥2 gate — it can
        # be informational even on edge cases (no current contract path puts
        # it on seq=1, but surface it whenever present for ops audit).
        reason = alert.get("engineer_required_reason")
        if reason:
            card.engineer_required_reason = reason
    return card


async def _latest_accepted_inbox(db: AsyncSession, request_number: str) -> WebhookInbox | None:
    """Return the most recent accepted webhook_inbox row for the request, or None.

    Defensive ORDER BY id DESC LIMIT 1: in normal operation there's exactly
    one inbox row per infrasafe-originated request (alert.created or
    alert.engineer_required → accepted), but ordering protects against any
    future contract where a request_number is reused across replays.
    """
    return await db.scalar(
        select(WebhookInbox)
        .where(
            WebhookInbox.request_number == request_number,
            WebhookInbox.outcome == "accepted",
        )
        .order_by(WebhookInbox.id.desc())
        .limit(1)
    )


@router.get("/kanban", response_model=KanbanResponse)
async def get_kanban(
    executor_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    ExecutorUser = aliased(User)
    query = (
        select(RequestModel, ExecutorUser)
        .outerjoin(ExecutorUser, RequestModel.executor_id == ExecutorUser.id)
    )
    if executor_id:
        query = query.filter(RequestModel.executor_id == executor_id)
    if category:
        query = query.filter(RequestModel.category == category)

    result = await db.execute(query.order_by(RequestModel.created_at.desc()).limit(500))
    rows = result.all()

    columns = []
    for st in KANBAN_STATUSES:
        st_cards = [_make_request_card(r, eu) for r, eu in rows if r.status == st]
        columns.append(KanbanColumn(status=st, count=len(st_cards), requests=st_cards))
    return KanbanResponse(columns=columns)


@router.get("", response_model=list[RequestCard])
async def list_requests(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    executor_id: Optional[int] = Query(None),
    source: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ExecutorUser = aliased(User)
    query = (
        select(RequestModel, ExecutorUser)
        .outerjoin(ExecutorUser, RequestModel.executor_id == ExecutorUser.id)
    )
    # Server-enforced object-level scoping: only managers may list across all
    # users. For everyone else, ownership/assignment filtering is applied
    # unconditionally (the client-supplied `scope` param is not an authz input).
    user_roles = _parse_user_roles(user)
    if "manager" not in user_roles:
        if "executor" in user_roles:
            # Executor: individual assignments + group (if in shift) + executor_id fallback
            from sqlalchemy import or_
            from uk_management_bot.database.models.request_assignment import RequestAssignment
            from uk_management_bot.database.models.shift import Shift
            import json as _json

            conditions = []
            # 1. Individual assignments
            assignment_sub = select(RequestAssignment.request_number).where(
                RequestAssignment.executor_id == user.id,
                RequestAssignment.status == "active",
            )
            conditions.append(RequestModel.request_number.in_(assignment_sub))
            # 2. Group assignments (only if executor has active shift)
            active_shift = await db.execute(
                select(Shift).where(Shift.user_id == user.id, Shift.status == "active")
            )
            if active_shift.scalars().first():
                specs = []
                if user.specialization:
                    try:
                        raw = user.specialization
                        if isinstance(raw, str) and raw.startswith("["):
                            specs = _json.loads(raw)
                        else:
                            specs = [raw] if raw else []
                    except Exception:
                        specs = [user.specialization] if user.specialization else []
                if specs:
                    group_sub = select(RequestAssignment.request_number).where(
                        RequestAssignment.assignment_type == "group",
                        RequestAssignment.group_specialization.in_(specs),
                        RequestAssignment.status == "active",
                    )
                    conditions.append(RequestModel.request_number.in_(group_sub))
            # 3. Fallback: executor_id
            conditions.append(RequestModel.executor_id == user.id)
            query = query.filter(or_(*conditions))
        else:
            # Applicant: own requests only
            query = query.filter(RequestModel.user_id == user.id)
    if status:
        query = query.filter(RequestModel.status == status)
    if category:
        query = query.filter(RequestModel.category == category)
    if executor_id:
        query = query.filter(RequestModel.executor_id == executor_id)
    if source:
        query = query.filter(RequestModel.source == source)

    result = await db.execute(query.order_by(RequestModel.created_at.desc()).offset(offset).limit(limit))
    return [_make_request_card(r, eu) for r, eu in result.all()]


@router.get("/acceptance", response_model=list[RequestCard])
async def get_acceptance_requests(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Requests pending acceptance: own + apartment neighbors, status=Исполнено."""
    from sqlalchemy import or_
    from uk_management_bot.database.models.user_apartment import UserApartment

    apt_result = await db.execute(
        select(UserApartment.apartment_id).where(
            UserApartment.user_id == user.id,
            UserApartment.status == "approved",
        )
    )
    apt_ids = [row[0] for row in apt_result.all()]

    conditions = [RequestModel.user_id == user.id]
    if apt_ids:
        conditions.append(RequestModel.apartment_id.in_(apt_ids))

    ExecutorUser = aliased(User)
    result = await db.execute(
        select(RequestModel, ExecutorUser)
        .outerjoin(ExecutorUser, RequestModel.executor_id == ExecutorUser.id)
        .where(
            or_(*conditions),
            RequestModel.status == "Исполнено",
        )
        .order_by(RequestModel.updated_at.desc())
        .limit(20)
    )
    return [_make_request_card(r, eu) for r, eu in result.all()]


@router.get("/{request_number}", response_model=RequestCard)
async def get_request(
    request_number: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Access check (owner, executor, manager, apartment resident for acceptance)
    await check_request_access(request_number, db, user)

    ExecutorUser = aliased(User)
    result = await db.execute(
        select(RequestModel, ExecutorUser)
        .outerjoin(ExecutorUser, RequestModel.executor_id == ExecutorUser.id)
        .where(RequestModel.request_number == request_number)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    req, exec_user = row
    # INT-120 #3 — detail endpoint enriches with reopen-meta from webhook_inbox
    # (list endpoints skip this to keep their cost identical to the baseline).
    inbox_row = await _latest_accepted_inbox(db, request_number)
    return _make_request_card(req, exec_user, inbox_row=inbox_row)


@router.post("", response_model=RequestCard, status_code=201)
@limiter.limit("20/minute")
async def create_request(
    request: Request,
    body: CreateRequestBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    today = date.today().strftime("%y%m%d")
    count_result = await db.execute(
        select(func.count(RequestModel.request_number)).where(
            RequestModel.request_number.like(f"{today}-%")
        )
    )
    count = count_result.scalar() or 0
    request_number = _generate_request_number(today, count)

    req = RequestModel(
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
    try:
        db.add(req)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        count_result = await db.execute(
            select(func.count(RequestModel.request_number)).where(
                RequestModel.request_number.like(f"{today}-%")
            )
        )
        count = count_result.scalar() or 0
        req.request_number = _generate_request_number(today, count)
        db.add(req)
        await db.commit()
    await db.refresh(req)

    await publish_request_event("request.created", RequestCard.model_validate(req).model_dump(mode="json"))
    # Webhook to InfraSafe (ARCH-113: shared builder, tagged source=api)
    await emit_request_created(db, req, source="api")
    await db.commit()
    return RequestCard.model_validate(req)


@router.patch("/{request_number}", response_model=RequestCard)
@limiter.limit("30/minute")
async def update_request(
    request: Request,
    request_number: str,
    body: UpdateRequestBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager", "applicant", "executor")),
):
    result = await db.execute(
        select(RequestModel).where(RequestModel.request_number == request_number).with_for_update()
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    user_roles = set(_parse_user_roles(user))
    updates = body.model_dump(exclude_unset=True)

    # ── Executor path ──
    if "executor" in user_roles and "manager" not in user_roles:
        # Check assignment (RequestAssignment OR executor_id fallback)
        from uk_management_bot.database.models.request_assignment import RequestAssignment
        assignments_result = await db.execute(
            select(RequestAssignment).where(
                RequestAssignment.request_number == request_number,
            )
        )
        assignments = assignments_result.scalars().all()
        if not is_assigned_executor(req, user, assignments):
            raise HTTPException(status_code=403, detail="Not assigned to this request")
        # Require active shift for status changes
        new_status = updates.get("status")
        if new_status:
            await require_active_shift(db, user)
            executor_transitions = {
                "Новая": {"В работе"},
                "В работе": {"Закуп", "Уточнение", "Выполнена"},
                "Закуп": {"В работе"},
                "Уточнение": {"В работе"},
            }
            allowed = executor_transitions.get(req.status, set())
            if new_status not in allowed:
                raise HTTPException(
                    status_code=422,
                    detail=f"Executor cannot transition from '{req.status}' to '{new_status}'",
                )
        # Executor can only update specific fields
        executor_fields = {"status", "completion_report", "requested_materials", "notes"}
        for field in list(updates.keys()):
            if field not in executor_fields:
                del updates[field]

    # ── Applicant path ──
    elif "applicant" in user_roles and "manager" not in user_roles:
        is_owner = req.user_id == user.id
        # Apartment co-resident can accept (Исполнено → Принято) only
        is_apartment_resident = False
        if not is_owner and req.apartment_id and req.status == "Исполнено":
            from uk_management_bot.database.models.user_apartment import UserApartment
            res = await db.execute(
                select(UserApartment).where(
                    UserApartment.user_id == user.id,
                    UserApartment.apartment_id == req.apartment_id,
                    UserApartment.status == "approved",
                )
            )
            is_apartment_resident = res.scalar_one_or_none() is not None
        if not is_owner and not is_apartment_resident:
            raise HTTPException(status_code=403, detail="Cannot update another user's request")
        allowed_fields = {"status", "rating"}
        unset_fields = set(updates.keys())
        if not unset_fields.issubset(allowed_fields):
            raise HTTPException(status_code=403, detail="Applicants can only update status and rating")

    # ── Status transition validation (all roles) ──
    new_status = updates.get("status")
    if new_status and new_status != req.status:
        allowed = _REQUEST_VALID_TRANSITIONS.get(req.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Transition '{req.status}' → '{new_status}' is not allowed"
            )

    old_status = req.status
    for field, value in updates.items():
        setattr(req, field, value)

    await db.commit()
    await db.refresh(req)

    if old_status != req.status:
        event_data = {"number": request_number, "old_status": old_status, "new_status": req.status}
        await publish_request_event("request.status_changed", event_data)
        # Webhook to InfraSafe (ARCH-113: shared builder, tagged source=api)
        await emit_request_status_changed(db, request_number, old_status, req.status, source="api")
        await db.commit()

    return RequestCard.model_validate(req)


@router.get("/{request_number}/comments", response_model=list[CommentOut])
async def get_comments(
    request_number: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Access check (owner, executor, manager, apartment resident for acceptance)
    await check_request_access(request_number, db, user)

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
    # Access check
    await check_request_access(request_number, db, user)

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


@router.post(
    "/{request_number}/remind-applicant",
    dependencies=[Depends(require_roles("manager"))],
)
async def remind_applicant(
    request_number: str,
    db: AsyncSession = Depends(get_db),
):
    """Send a Telegram reminder to the applicant to accept a completed request."""
    req_result = await db.execute(select(RequestModel).where(RequestModel.request_number == request_number))
    req = req_result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "Исполнено":
        raise HTTPException(status_code=422, detail="Request must be in 'Исполнено' status")

    applicant_result = await db.execute(select(User).where(User.id == req.user_id))
    applicant = applicant_result.scalar_one_or_none()
    if not applicant or not getattr(applicant, "telegram_id", None):
        raise HTTPException(status_code=404, detail="Applicant has no Telegram account")

    try:
        from uk_management_bot.services.notification_service import _get_shared_bot
        bot = _get_shared_bot()
        text = (
            f"🔔 <b>Напоминание о приёмке</b>\n\n"
            f"Заявка <code>{req.request_number}</code> — <b>{req.category}</b>\n"
            f"выполнена и ожидает вашей приёмки.\n\n"
            f"Пожалуйста, проверьте выполненную работу и подтвердите через приложение."
        )
        await bot.send_message(chat_id=applicant.telegram_id, text=text, parse_mode="HTML")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send reminder: {e}")
