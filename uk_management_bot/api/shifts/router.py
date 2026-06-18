import logging
import httpx
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_roles, _parse_user_roles
from uk_management_bot.api.shifts import service
from uk_management_bot.api.shifts.schemas import (
    EmployeeBrief, EmployeeDetail,
    ShiftBrief, ShiftDetail,
    TransferOut, ShiftStatsOut,
    CreateShiftBody, UpdateShiftBody,
    CreateFromTemplateBody, HandleTransferBody,
    TemplateBrief, CreateTemplateBody, UpdateTemplateBody,
    DeleteEmployeeRequest, ActiveRequestsCount,
    CreateInviteRequest, CreateInviteResponse, CreateEmployeeRequest,
)
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User
from uk_management_bot.services.redis_pubsub import publish_shift_event

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers (no direct ORM — pure serializers / non-DB utilities)
# ---------------------------------------------------------------------------

async def _resolve_bot_username() -> Optional[str]:
    """Return the bot @username used to build invite links.

    The bot process (main.py) self-heals BOT_USERNAME via getMe() at startup
    (BUG-BOT-001), but invite links are built by *this* API process, which only
    reads os.getenv("BOT_USERNAME"). If the var is missing from the API
    environment, the link would render as https://t.me/None. Mirror the bot's
    behaviour here: resolve via Telegram getMe() using BOT_TOKEN and cache the
    result back into settings so subsequent requests skip the network.

    Returns None only when resolution is impossible (no token / API failure),
    so the caller can fail loudly instead of emitting a broken link.
    """
    from uk_management_bot.config.settings import settings as app_settings

    if app_settings.BOT_USERNAME:
        return app_settings.BOT_USERNAME

    token = app_settings.BOT_TOKEN
    if not token:
        logger.error("Cannot resolve bot username: BOT_USERNAME and BOT_TOKEN are both unset")
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            resp.raise_for_status()
            username = (resp.json().get("result") or {}).get("username")
    except Exception as exc:  # network/auth issues — never crash the request
        logger.error(f"getMe() failed while resolving bot username for invite link: {exc}")
        return None

    if username:
        app_settings.BOT_USERNAME = username  # cache for subsequent requests
        logger.info(f"Resolved bot username via getMe(): {username}")
    return username


def _executor_name(user: Optional[User]) -> Optional[str]:
    if user is None:
        return None
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return name or None


def _shift_brief(shift: Shift, user: Optional[User] = None) -> ShiftBrief:
    load_pct = (shift.current_request_count / shift.max_requests * 100) if shift.max_requests > 0 else 0.0
    return ShiftBrief(
        id=shift.id,
        user_id=shift.user_id,
        executor_name=_executor_name(user),
        status=shift.status,
        shift_type=shift.shift_type,
        start_time=shift.start_time,
        end_time=shift.end_time,
        max_requests=shift.max_requests,
        current_request_count=shift.current_request_count,
        load_percentage=load_pct,
        specialization_focus=shift.specialization_focus,
    )


def _shift_detail(shift: Shift, user: Optional[User] = None) -> ShiftDetail:
    load_pct = (shift.current_request_count / shift.max_requests * 100) if shift.max_requests > 0 else 0.0
    return ShiftDetail(
        id=shift.id,
        user_id=shift.user_id,
        executor_name=_executor_name(user),
        status=shift.status,
        shift_type=shift.shift_type,
        start_time=shift.start_time,
        end_time=shift.end_time,
        max_requests=shift.max_requests,
        current_request_count=shift.current_request_count,
        load_percentage=load_pct,
        notes=shift.notes,
        specialization_focus=shift.specialization_focus,
        coverage_areas=shift.coverage_areas,
        priority_level=shift.priority_level,
        completed_requests=shift.completed_requests,
        efficiency_score=shift.efficiency_score,
        quality_rating=shift.quality_rating,
        template_id=shift.shift_template_id,
        created_at=shift.created_at,
    )


def _ensure_not_privileged(user: User, *, action: str) -> None:
    """Raise 403 if the target user is a manager/admin (cannot be modified)."""
    target_roles = set(_parse_user_roles(user))
    if "manager" in target_roles or "admin" in target_roles:
        raise HTTPException(status_code=403, detail=action)


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------

@router.get("/employees", response_model=list[EmployeeBrief])
async def list_employees(
    specialization: Optional[str] = Query(None),
    has_active_shift: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    verification_status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    users, active_shifts = await service.list_employees(
        db,
        specialization=specialization,
        has_active_shift=has_active_shift,
        search=search,
        role=role,
        verification_status=verification_status,
        limit=limit,
        offset=offset,
    )

    briefs = []
    for u in users:
        # Inject active_shift_id into the object so model_validator can see it
        u.__dict__['active_shift_id'] = active_shifts.get(u.id)
        briefs.append(EmployeeBrief.model_validate(u))
    return briefs


@router.post("/employees", response_model=EmployeeBrief, status_code=201)
async def create_employee(
    body: CreateEmployeeRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    """Create an employee directly from the web dashboard."""
    user = await service.create_employee(
        db,
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        role=body.role,
        specializations=body.specializations,
        status=body.status,
    )
    user.__dict__['active_shift_id'] = None
    return EmployeeBrief.model_validate(user)


@router.post("/employees/invite", response_model=CreateInviteResponse, status_code=201)
async def create_invite(
    body: CreateInviteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("manager")),
):
    """Generate an invite token for a new employee to join via the Telegram bot."""
    import asyncio
    from uk_management_bot.database.session import SessionLocal
    from uk_management_bot.services.invite_service import InviteService
    from datetime import timedelta

    spec_str = ",".join(body.specializations) if body.specializations else None

    # Resolve the bot username up front: if it can't be determined we must not
    # generate a token only to hand back a broken https://t.me/None link.
    bot_username = await _resolve_bot_username()
    if not bot_username:
        raise HTTPException(
            status_code=503,
            detail="Bot username unavailable — set BOT_USERNAME in the API environment.",
        )

    def _generate():
        sync_db = SessionLocal()
        try:
            svc = InviteService(sync_db)
            token = svc.generate_invite(
                role=body.role,
                created_by=current_user.telegram_id,
                specialization=spec_str,
                hours=body.hours,
            )
            return token
        finally:
            sync_db.close()

    loop = asyncio.get_running_loop()
    token = await loop.run_in_executor(None, _generate)

    expires_at = datetime.now(timezone.utc) + timedelta(hours=body.hours)

    return CreateInviteResponse(
        token=token,
        bot_link=f"https://t.me/{bot_username}",
        expires_at=expires_at,
    )


@router.patch("/employees/{user_id}/approve", dependencies=[Depends(require_roles("manager"))])
async def approve_employee(user_id: int, db: AsyncSession = Depends(get_db)):
    """Approve a pending user (set verification_status = 'verified')"""
    user = await service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_not_privileged(user, action="Cannot modify status of a manager or admin user")
    if user.verification_status == "verified":
        raise HTTPException(status_code=409, detail="User is already verified")
    if user.verification_status == "rejected":
        raise HTTPException(status_code=409, detail="User was rejected and cannot be re-approved this way")
    await service.set_user_verification(db, user, "verified")
    return {"id": user.id, "verification_status": user.verification_status}


@router.patch("/employees/{user_id}/reject", dependencies=[Depends(require_roles("manager"))])
async def reject_employee(user_id: int, db: AsyncSession = Depends(get_db)):
    """Reject a pending user (set verification_status = 'rejected')"""
    user = await service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_not_privileged(user, action="Cannot modify status of a manager or admin user")
    if user.verification_status == "rejected":
        raise HTTPException(status_code=409, detail="User is already rejected")
    await service.set_user_verification(db, user, "rejected")
    return {"id": user.id, "verification_status": user.verification_status}


@router.patch("/employees/{user_id}/block", dependencies=[Depends(require_roles("manager"))])
async def block_employee(user_id: int, db: AsyncSession = Depends(get_db)):
    """Block an employee — sets status='blocked', preventing system access."""
    user = await service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_not_privileged(user, action="Cannot modify status of a manager or admin user")
    if user.status == "blocked":
        raise HTTPException(status_code=409, detail="User is already blocked")
    await service.set_user_status(db, user, "blocked")
    return {"message": "blocked"}


@router.patch("/employees/{user_id}/unblock", dependencies=[Depends(require_roles("manager"))])
async def unblock_employee(user_id: int, db: AsyncSession = Depends(get_db)):
    """Unblock an employee — sets status back to 'approved'."""
    user = await service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_not_privileged(user, action="Cannot modify status of a manager or admin user")
    if user.status != "blocked":
        raise HTTPException(status_code=409, detail="User is not blocked")
    await service.set_user_status(db, user, "approved")
    return {"message": "unblocked"}


@router.get("/employees/{user_id}/active-requests-count", response_model=ActiveRequestsCount)
async def get_active_requests_count(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    """Return number of active requests assigned to this employee."""
    count = await service.count_active_requests(db, user_id)
    return ActiveRequestsCount(count=count)


@router.patch("/employees/{user_id}/delete")
async def delete_employee(
    user_id: int,
    body: DeleteEmployeeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("manager")),
):
    """Soft-delete an employee, optionally reassigning their active requests."""
    user = await service.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    _ensure_not_privileged(user, action="Cannot delete a manager or admin user")

    if user.deleted_at is not None:
        raise HTTPException(status_code=409, detail="User is already deleted")

    active_count = await service.count_active_requests(db, user_id)

    if active_count > 0 and body.reassign_to is None:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Employee has active requests that must be reassigned",
                "active_requests_count": active_count,
            },
        )

    if body.reassign_to is not None and active_count > 0:
        target_user = await service.get_user(db, body.reassign_to)
        if not target_user:
            raise HTTPException(status_code=404, detail="Target employee not found")
        if target_user.deleted_at is not None:
            raise HTTPException(status_code=422, detail="Cannot reassign to a deleted employee")

    await service.soft_delete_employee(
        db,
        user=user,
        reassign_to=body.reassign_to,
        reason=body.reason,
        deleted_by_id=current_user.id,
        active_count=active_count,
    )
    return {"message": "deleted", "reassigned_requests": active_count if body.reassign_to else 0}


@router.get("/employees/{user_id}", response_model=EmployeeDetail)
async def get_employee(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    data = await service.get_employee_with_stats(db, user_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    emp, active_shift_obj, total_shifts, total_completed, rating = data

    active_shift_brief = _shift_brief(active_shift_obj) if active_shift_obj else None

    emp.__dict__['active_shift_id'] = active_shift_obj.id if active_shift_obj else None
    brief = EmployeeBrief.model_validate(emp)

    return EmployeeDetail(
        **brief.model_dump(),
        active_shift=active_shift_brief,
        rating=rating,
        total_shifts=total_shifts,
        total_completed=total_completed,
    )


# ---------------------------------------------------------------------------
# Shifts CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ShiftBrief])
async def list_shifts(
    status: Optional[str] = Query(None),
    shift_type: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    shifts, users_map = await service.list_shifts(
        db,
        status=status,
        shift_type=shift_type,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return [_shift_brief(s, users_map.get(s.user_id) if s.user_id else None) for s in shifts]


@router.get("/schedule", response_model=list[ShiftBrief])
async def get_schedule(
    date_from: datetime = Query(...),
    date_to: datetime = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    if date_to < date_from:
        raise HTTPException(status_code=422, detail="date_to must be >= date_from")
    if (date_to - date_from).days > 90:
        raise HTTPException(status_code=422, detail="Date range cannot exceed 90 days")
    shifts, users_map = await service.get_schedule(db, date_from=date_from, date_to=date_to)
    return [_shift_brief(s, users_map.get(s.user_id) if s.user_id else None) for s in shifts]


@router.get("/stats", response_model=ShiftStatsOut)
async def get_stats(
    period: str = Query("7d"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    # Parse period
    days = 7
    if period.endswith("d"):
        try:
            days = int(period[:-1])
        except ValueError:
            days = 7
    days = max(1, min(days, 365))

    from datetime import timedelta
    period_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    period_start = period_start - timedelta(days=days - 1)

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59, microsecond=999999)

    stats = await service.get_stats(
        db, period_start=period_start, today_start=today_start, today_end=today_end
    )

    total_executors = stats["total_executors"]
    active_executors = stats["active_executors"]
    coverage_pct = (active_executors / total_executors * 100) if total_executors > 0 else 0.0

    return ShiftStatsOut(
        active_shifts=stats["active_shifts"],
        active_executors=active_executors,
        coverage_pct=round(coverage_pct, 1),
        avg_efficiency=stats["avg_efficiency"],
        shifts_today=stats["shifts_today"],
        pending_transfers=stats["pending_transfers"],
    )


@router.get("/transfers", response_model=list[TransferOut])
async def list_transfers(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    rows = await service.list_transfers(db, limit=limit, offset=offset)
    out = []
    for transfer, fu, tu in rows:
        out.append(TransferOut(
            id=transfer.id,
            shift_id=transfer.shift_id,
            from_executor_name=_executor_name(fu),
            to_executor_name=_executor_name(tu) if tu else None,
            status=transfer.status,
            reason=transfer.reason,
            urgency_level=transfer.urgency_level,
            comment=transfer.comment,
            created_at=transfer.created_at,
        ))
    return out


@router.get("/templates", response_model=list[TemplateBrief])
async def list_templates(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    templates = await service.list_templates(db, limit=limit, offset=offset)
    return [TemplateBrief.model_validate(t) for t in templates]


@router.get("/templates/{template_id}", response_model=TemplateBrief)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    tmpl = await service.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return TemplateBrief.model_validate(tmpl)


@router.post("/templates", response_model=TemplateBrief, status_code=201)
async def create_template(
    body: CreateTemplateBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    tmpl = await service.create_template(db, body=body)
    return TemplateBrief.model_validate(tmpl)


@router.patch("/templates/{template_id}", response_model=TemplateBrief)
async def update_template(
    template_id: int,
    body: UpdateTemplateBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    tmpl = await service.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    tmpl = await service.update_template(
        db, tmpl=tmpl, fields=body.model_dump(exclude_unset=True)
    )
    return TemplateBrief.model_validate(tmpl)


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    tmpl = await service.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    await service.soft_delete_template(db, tmpl=tmpl)
    return {"message": "deleted"}


@router.post("/from-template", response_model=list[ShiftDetail], status_code=201)
async def create_from_template(
    body: CreateFromTemplateBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    tmpl = await service.get_active_template(db, body.template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    # Recurrence (days_of_week / cycle) НЕ применяется здесь намеренно: менеджер
    # выбрал конкретную дату вручную — это осознанный разовый override правил
    # повторения шаблона.
    target_date = body.date

    start_dt = datetime(
        target_date.year, target_date.month, target_date.day,
        tmpl.start_hour, tmpl.start_minute or 0,
        tzinfo=timezone.utc,
    )
    from datetime import timedelta
    end_dt = start_dt + timedelta(hours=tmpl.duration_hours or 8)

    user_ids = body.user_ids
    if not user_ids:
        raise HTTPException(status_code=422, detail="user_ids must not be empty")

    # Batch-load and validate all users upfront
    users_map = await service.load_users_map(db, user_ids)
    missing = [uid for uid in user_ids if uid not in users_map]
    if missing:
        raise HTTPException(status_code=404, detail=f"Users not found: {missing}")

    created_shifts = await service.create_shifts_from_template(
        db, tmpl=tmpl, user_ids=user_ids, start_dt=start_dt, end_dt=end_dt
    )

    return [_shift_detail(s, users_map.get(s.user_id) if s.user_id else None) for s in created_shifts]


@router.post("/transfers/{transfer_id}/handle", response_model=TransferOut)
async def handle_transfer(
    transfer_id: int,
    body: HandleTransferBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    transfer = await service.get_transfer_for_update(db, transfer_id)
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")

    action = body.action

    if action == "approve":
        if transfer.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot approve transfer in status '{transfer.status}' — expected 'pending'",
            )
        if body.to_executor_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="to_executor_id is required for action 'approve'",
            )
        # Validate target executor exists and has executor role
        new_executor = await service.get_user(db, body.to_executor_id)
        if not new_executor:
            raise HTTPException(status_code=404, detail="Executor not found")
        has_exec_role = "executor" in _parse_user_roles(new_executor)
        if not has_exec_role:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Target user does not have executor role",
            )
        await service.approve_transfer(db, transfer=transfer, to_executor_id=body.to_executor_id)

    elif action == "reject":
        if transfer.status != "assigned":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot reject transfer in status '{transfer.status}' — expected 'assigned'",
            )
        the_shift = await service.reject_transfer(db, transfer=transfer)
        if the_shift is None:
            logger.warning(
                "Shift %s not found when rejecting transfer %s — shift.user_id not restored",
                transfer.shift_id, transfer.id
            )

    elif action == "cancel":
        if transfer.status not in ("pending", "assigned"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot cancel transfer in status '{transfer.status}'",
            )
        service.cancel_transfer(transfer)

    await service.commit_and_refresh_transfer(db, transfer)

    # Resolve executor names
    from_user, to_user = await service.resolve_transfer_users(db, transfer)

    transfer_out = TransferOut(
        id=transfer.id,
        shift_id=transfer.shift_id,
        from_executor_name=_executor_name(from_user),
        to_executor_name=_executor_name(to_user) if to_user else None,
        status=transfer.status,
        reason=transfer.reason,
        urgency_level=transfer.urgency_level,
        comment=transfer.comment,
        created_at=transfer.created_at,
    )

    await publish_shift_event("transfer.updated", transfer_out.model_dump(mode="json"))
    return transfer_out


@router.get("/{shift_id}", response_model=ShiftDetail)
async def get_shift(
    shift_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    shift = await service.get_shift(db, shift_id)
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    user_obj = None
    if shift.user_id:
        user_obj = await service.get_user(db, shift.user_id)

    return _shift_detail(shift, user_obj)


@router.post("", response_model=ShiftDetail, status_code=201)
async def create_shift(
    body: CreateShiftBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    # Validate executor exists and has executor role
    emp = await service.get_user(db, body.user_id)
    if not emp:
        raise HTTPException(status_code=404, detail="User not found")

    has_executor_role = "executor" in _parse_user_roles(emp)
    if not has_executor_role:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="User does not have executor role",
        )

    # Check for overlapping active or planned shifts
    overlap = await service.find_overlapping_shift_for_update(
        db, user_id=body.user_id, start_time=body.start_time, end_time=body.end_time,
    )
    if overlap:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already has an active shift overlapping with the requested time range",
        )

    shift = await service.create_shift(db, body=body)

    detail = _shift_detail(shift, emp)
    await publish_shift_event("shift.created", detail.model_dump(mode="json"))
    return detail


@router.patch("/{shift_id}", response_model=ShiftDetail)
async def update_shift(
    shift_id: int,
    body: UpdateShiftBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    shift = await service.get_shift(db, shift_id)
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    if body.status is not None:
        VALID_TRANSITIONS: dict[str, list[str]] = {
            "planned": ["active", "cancelled"],
            "active": ["paused", "cancelled"],
            "paused": ["active", "cancelled"],
        }
        allowed = VALID_TRANSITIONS.get(shift.status, [])
        if body.status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Transition '{shift.status}' → '{body.status}' is not allowed",
            )

    if body.user_id is not None and body.user_id != shift.user_id:
        new_user = await service.get_user(db, body.user_id)
        if not new_user:
            raise HTTPException(status_code=404, detail="Target user not found")
        if "executor" not in _parse_user_roles(new_user):
            raise HTTPException(status_code=422, detail="Target user does not have executor role")

    data = body.model_dump(exclude_unset=True)

    # Content edits (anything other than a status transition) are only allowed
    # while the shift is still editable — not after it is completed/cancelled.
    EDITABLE_STATUSES = {"planned", "active", "paused"}
    content = {k: v for k, v in data.items() if k != "status"}
    if content and shift.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot edit a '{shift.status}' shift",
        )

    # Normalise incoming times to tz-aware UTC so they compare/store consistently
    # with the DB columns (DateTime(timezone=True)); a client may omit the offset.
    for key in ("start_time", "end_time"):
        if data.get(key) is not None and data[key].tzinfo is None:
            data[key] = data[key].replace(tzinfo=timezone.utc)

    # Validate time order against effective values (incoming or existing).
    new_start = data.get("start_time", shift.start_time)
    new_end = data.get("end_time", shift.end_time)
    if new_start is not None and new_end is not None and new_end <= new_start:
        raise HTTPException(status_code=422, detail="end_time must be after start_time")

    # Prevent double-booking when the time window or executor changes
    # (mirrors the overlap check in create_shift, excluding this shift itself).
    if ("start_time" in data or "end_time" in data or "user_id" in data) \
            and new_start is not None and new_end is not None:
        target_user_id = data.get("user_id", shift.user_id)
        overlap = await service.find_overlapping_shift_for_update(
            db, user_id=target_user_id, start_time=new_start, end_time=new_end,
            exclude_shift_id=shift_id, lock=False,
        )
        if overlap:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already has an active shift overlapping with the requested time range",
            )

    shift = await service.apply_shift_update(db, shift=shift, data=data)

    user_obj = None
    if shift.user_id:
        user_obj = await service.get_user(db, shift.user_id)

    detail = _shift_detail(shift, user_obj)
    await publish_shift_event("shift.updated", detail.model_dump(mode="json"))
    return detail


@router.delete("/{shift_id}")
async def delete_shift(
    shift_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    shift = await service.get_shift(db, shift_id)
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    if shift.status != "planned":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only planned shifts can be deleted — current status is '{shift.status}'",
        )

    await service.delete_shift(db, shift=shift)
    return {"message": "deleted"}


@router.post("/{shift_id}/end", response_model=ShiftDetail)
async def end_shift(
    shift_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    shift = await service.get_shift(db, shift_id)
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    if shift.status not in ("active", "paused"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot end shift with status '{shift.status}'",
        )

    shift = await service.end_shift(db, shift=shift)

    user_obj = None
    if shift.user_id:
        user_obj = await service.get_user(db, shift.user_id)

    detail = _shift_detail(shift, user_obj)
    await publish_shift_event("shift.ended", detail.model_dump(mode="json"))
    return detail
