import re
import logging
from datetime import datetime, timezone, date as date_type
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import aliased

from uk_management_bot.api.dependencies import get_db, get_current_user, require_roles, _parse_user_roles
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
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_template import ShiftTemplate
from uk_management_bot.database.models.shift_transfer import ShiftTransfer
from uk_management_bot.database.models.user import User
from uk_management_bot.services.redis_pubsub import publish_shift_event

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _escape_like(value: str) -> str:
    """Escape SQL LIKE wildcards % _ \\ to prevent injection."""
    return re.sub(r'([%_\\])', r'\\\1', value)

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
    query = select(User).where(
        or_(
            User.role == "executor",
            User.roles.like('%"executor"%'),
        ),
        User.deleted_at.is_(None),
    )

    if specialization:
        query = query.where(User.specialization.like(f'%{_escape_like(specialization)}%'))

    if search:
        search_term = f"%{_escape_like(search)}%"
        query = query.where(
            or_(
                User.first_name.ilike(search_term),
                User.last_name.ilike(search_term),
                User.phone.ilike(search_term),
            )
        )
    if verification_status:
        query = query.where(User.verification_status == verification_status)
    if role:
        query = query.where(User.roles.like(f'%"{_escape_like(role)}"%'))

    if has_active_shift is True:
        active_shift_subq = (
            select(Shift.user_id)
            .where(Shift.status == "active")
            .scalar_subquery()
        )
        query = query.where(User.id.in_(active_shift_subq))
    elif has_active_shift is False:
        active_shift_subq = (
            select(Shift.user_id)
            .where(Shift.status == "active")
            .scalar_subquery()
        )
        query = query.where(User.id.not_in(active_shift_subq))

    result = await db.execute(query.offset(offset).limit(limit))
    users = result.scalars().all()

    # For each user, find their active shift id
    user_ids = [u.id for u in users]
    active_shifts: dict[int, int] = {}
    if user_ids:
        shift_result = await db.execute(
            select(Shift.user_id, Shift.id)
            .where(Shift.status == "active", Shift.user_id.in_(user_ids))
        )
        for uid, sid in shift_result.all():
            active_shifts[uid] = sid

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
    import time as _time
    import json as _json

    # Generate a negative placeholder telegram_id (real Telegram IDs are always positive)
    placeholder_tid = -abs(int(_time.time() * 1000))

    roles_list = [body.role]
    user = User(
        telegram_id=placeholder_tid,
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        role=body.role,
        roles=_json.dumps(roles_list),
        active_role=body.role,
        specialization=_json.dumps(body.specializations) if body.specializations else None,
        status=body.status,
        verification_status="verified" if body.status == "approved" else "pending",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

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
    from uk_management_bot.config.settings import settings as app_settings
    from datetime import timedelta

    spec_str = ",".join(body.specializations) if body.specializations else None

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

    bot_username = app_settings.BOT_USERNAME
    expires_at = datetime.now(timezone.utc) + timedelta(hours=body.hours)

    return CreateInviteResponse(
        token=token,
        bot_link=f"https://t.me/{bot_username}",
        expires_at=expires_at,
    )


@router.patch("/employees/{user_id}/approve", dependencies=[Depends(require_roles("manager"))])
async def approve_employee(user_id: int, db: AsyncSession = Depends(get_db)):
    """Approve a pending user (set verification_status = 'verified')"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    target_roles = set(_parse_user_roles(user))
    if "manager" in target_roles or "admin" in target_roles:
        raise HTTPException(
            status_code=403,
            detail="Cannot modify status of a manager or admin user"
        )
    if user.verification_status == "verified":
        raise HTTPException(status_code=409, detail="User is already verified")
    if user.verification_status == "rejected":
        raise HTTPException(status_code=409, detail="User was rejected and cannot be re-approved this way")
    user.verification_status = "verified"
    await db.commit()
    await db.refresh(user)
    return {"id": user.id, "verification_status": user.verification_status}


@router.patch("/employees/{user_id}/reject", dependencies=[Depends(require_roles("manager"))])
async def reject_employee(user_id: int, db: AsyncSession = Depends(get_db)):
    """Reject a pending user (set verification_status = 'rejected')"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    target_roles = set(_parse_user_roles(user))
    if "manager" in target_roles or "admin" in target_roles:
        raise HTTPException(
            status_code=403,
            detail="Cannot modify status of a manager or admin user"
        )
    if user.verification_status == "rejected":
        raise HTTPException(status_code=409, detail="User is already rejected")
    user.verification_status = "rejected"
    await db.commit()
    await db.refresh(user)
    return {"id": user.id, "verification_status": user.verification_status}


@router.patch("/employees/{user_id}/block", dependencies=[Depends(require_roles("manager"))])
async def block_employee(user_id: int, db: AsyncSession = Depends(get_db)):
    """Block an employee — sets status='blocked', preventing system access."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    target_roles = set(_parse_user_roles(user))
    if "manager" in target_roles or "admin" in target_roles:
        raise HTTPException(
            status_code=403,
            detail="Cannot modify status of a manager or admin user"
        )
    if user.status == "blocked":
        raise HTTPException(status_code=409, detail="User is already blocked")
    user.status = "blocked"
    await db.commit()
    return {"message": "blocked"}


@router.patch("/employees/{user_id}/unblock", dependencies=[Depends(require_roles("manager"))])
async def unblock_employee(user_id: int, db: AsyncSession = Depends(get_db)):
    """Unblock an employee — sets status back to 'approved'."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    target_roles = set(_parse_user_roles(user))
    if "manager" in target_roles or "admin" in target_roles:
        raise HTTPException(
            status_code=403,
            detail="Cannot modify status of a manager or admin user"
        )
    if user.status != "blocked":
        raise HTTPException(status_code=409, detail="User is not blocked")
    user.status = "approved"
    await db.commit()
    return {"message": "unblocked"}


ACTIVE_REQUEST_STATUSES = {"В работе", "Закуп", "Уточнение", "Выполнена", "Исполнено"}


@router.get("/employees/{user_id}/active-requests-count", response_model=ActiveRequestsCount)
async def get_active_requests_count(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    """Return number of active requests assigned to this employee."""
    result = await db.execute(
        select(func.count()).select_from(Request).where(
            Request.executor_id == user_id,
            Request.status.in_(ACTIVE_REQUEST_STATUSES),
        )
    )
    return ActiveRequestsCount(count=result.scalar() or 0)


@router.patch("/employees/{user_id}/delete")
async def delete_employee(
    user_id: int,
    body: DeleteEmployeeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("manager")),
):
    """Soft-delete an employee, optionally reassigning their active requests."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    target_roles = set(_parse_user_roles(user))
    if "manager" in target_roles or "admin" in target_roles:
        raise HTTPException(status_code=403, detail="Cannot delete a manager or admin user")

    if user.deleted_at is not None:
        raise HTTPException(status_code=409, detail="User is already deleted")

    # Count active requests
    count_result = await db.execute(
        select(func.count()).select_from(Request).where(
            Request.executor_id == user_id,
            Request.status.in_(ACTIVE_REQUEST_STATUSES),
        )
    )
    active_count = count_result.scalar() or 0

    if active_count > 0 and body.reassign_to is None:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Employee has active requests that must be reassigned",
                "active_requests_count": active_count,
            },
        )

    # Reassign active requests
    if body.reassign_to is not None and active_count > 0:
        target_result = await db.execute(select(User).where(User.id == body.reassign_to))
        target_user = target_result.scalar_one_or_none()
        if not target_user:
            raise HTTPException(status_code=404, detail="Target employee not found")
        if target_user.deleted_at is not None:
            raise HTTPException(status_code=422, detail="Cannot reassign to a deleted employee")

        # Bulk update executor_id on active requests
        active_requests_result = await db.execute(
            select(Request).where(
                Request.executor_id == user_id,
                Request.status.in_(ACTIVE_REQUEST_STATUSES),
            )
        )
        for req in active_requests_result.scalars().all():
            req.executor_id = body.reassign_to

    # Soft-delete the user
    user.deleted_at = datetime.now(timezone.utc)
    user.deleted_by = current_user.id
    user.deletion_reason = body.reason
    user.status = "deleted"

    # End any active shift
    active_shifts_result = await db.execute(
        select(Shift).where(Shift.user_id == user_id, Shift.status.in_(["active", "paused"]))
    )
    for shift in active_shifts_result.scalars().all():
        shift.status = "completed"
        shift.end_time = datetime.now(timezone.utc)

    await db.commit()
    return {"message": "deleted", "reassigned_requests": active_count if body.reassign_to else 0}


@router.get("/employees/{user_id}", response_model=EmployeeDetail)
async def get_employee(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    result = await db.execute(select(User).where(User.id == user_id))
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Active shift
    shift_result = await db.execute(
        select(Shift).where(Shift.user_id == user_id, Shift.status == "active")
    )
    active_shift_obj = shift_result.scalar_one_or_none()
    active_shift_brief = _shift_brief(active_shift_obj) if active_shift_obj else None

    # Stats
    total_result = await db.execute(
        select(func.count(Shift.id)).where(Shift.user_id == user_id)
    )
    total_shifts = total_result.scalar() or 0

    completed_result = await db.execute(
        select(func.count(Shift.id)).where(Shift.user_id == user_id, Shift.status == "completed")
    )
    total_completed = completed_result.scalar() or 0

    rating_result = await db.execute(
        select(func.avg(Shift.quality_rating)).where(
            Shift.user_id == user_id,
            Shift.status == "completed",
            Shift.quality_rating.isnot(None),
        )
    )
    rating = rating_result.scalar()

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
    query = select(Shift)
    if status:
        query = query.where(Shift.status == status)
    if shift_type:
        query = query.where(Shift.shift_type == shift_type)
    if user_id:
        query = query.where(Shift.user_id == user_id)
    if date_from:
        query = query.where(Shift.start_time >= date_from)
    if date_to:
        query = query.where(Shift.start_time <= date_to)

    result = await db.execute(query.order_by(Shift.start_time.desc()).offset(offset).limit(limit))
    shifts = result.scalars().all()

    # Batch load users for executor_name
    uids = list({s.user_id for s in shifts if s.user_id})
    users_map: dict[int, User] = {}
    if uids:
        u_result = await db.execute(select(User).where(User.id.in_(uids)))
        for u in u_result.scalars().all():
            users_map[u.id] = u

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
    result = await db.execute(
        select(Shift)
        .where(Shift.start_time >= date_from, Shift.start_time <= date_to)
        .order_by(Shift.start_time.asc())
    )
    shifts = result.scalars().all()

    uids = list({s.user_id for s in shifts if s.user_id})
    users_map: dict[int, User] = {}
    if uids:
        u_result = await db.execute(select(User).where(User.id.in_(uids)))
        for u in u_result.scalars().all():
            users_map[u.id] = u

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

    period_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    from datetime import timedelta
    period_start = period_start - timedelta(days=days - 1)

    # active_shifts
    active_count_result = await db.execute(
        select(func.count(Shift.id)).where(Shift.status == "active")
    )
    active_shifts = active_count_result.scalar() or 0

    # active_executors
    active_exec_result = await db.execute(
        select(func.count(func.distinct(Shift.user_id))).where(
            Shift.status == "active", Shift.user_id.isnot(None)
        )
    )
    active_executors = active_exec_result.scalar() or 0

    # total approved executors
    total_exec_result = await db.execute(
        select(func.count(User.id)).where(
            User.status == "approved",
            or_(
                User.role == "executor",
                User.roles.like('%"executor"%'),
            ),
        )
    )
    total_executors = total_exec_result.scalar() or 0
    coverage_pct = (active_executors / total_executors * 100) if total_executors > 0 else 0.0

    # avg_efficiency over period
    eff_result = await db.execute(
        select(func.avg(Shift.efficiency_score)).where(
            Shift.start_time >= period_start,
            Shift.efficiency_score.isnot(None),
        )
    )
    avg_efficiency = eff_result.scalar()

    # shifts_today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59, microsecond=999999)
    today_result = await db.execute(
        select(func.count(Shift.id)).where(
            Shift.start_time >= today_start,
            Shift.start_time <= today_end,
        )
    )
    shifts_today = today_result.scalar() or 0

    # pending_transfers
    pending_result = await db.execute(
        select(func.count(ShiftTransfer.id)).where(
            ShiftTransfer.status.in_(["pending", "assigned"])
        )
    )
    pending_transfers = pending_result.scalar() or 0

    return ShiftStatsOut(
        active_shifts=active_shifts,
        active_executors=active_executors,
        coverage_pct=round(coverage_pct, 1),
        avg_efficiency=avg_efficiency,
        shifts_today=shifts_today,
        pending_transfers=pending_transfers,
    )


@router.get("/transfers", response_model=list[TransferOut])
async def list_transfers(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    from_user = aliased(User)
    to_user = aliased(User)

    result = await db.execute(
        select(ShiftTransfer, from_user, to_user)
        .join(from_user, ShiftTransfer.from_executor_id == from_user.id)
        .outerjoin(to_user, ShiftTransfer.to_executor_id == to_user.id)
        .where(ShiftTransfer.status.in_(["pending", "assigned"]))
        .order_by(ShiftTransfer.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    rows = result.all()
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
    result = await db.execute(
        select(ShiftTemplate)
        .where(ShiftTemplate.is_active == True)  # noqa: E712
        .order_by(ShiftTemplate.id.asc())
        .offset(offset)
        .limit(limit)
    )
    return [TemplateBrief.model_validate(t) for t in result.scalars().all()]


@router.get("/templates/{template_id}", response_model=TemplateBrief)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    result = await db.execute(select(ShiftTemplate).where(ShiftTemplate.id == template_id))
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return TemplateBrief.model_validate(tmpl)


@router.post("/templates", response_model=TemplateBrief, status_code=201)
async def create_template(
    body: CreateTemplateBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    tmpl = ShiftTemplate(
        name=body.name,
        description=body.description,
        start_hour=body.start_hour,
        start_minute=body.start_minute,
        duration_hours=body.duration_hours,
        required_specializations=body.required_specializations or [],
        min_executors=body.min_executors,
        max_executors=body.max_executors,
        default_max_requests=body.default_max_requests,
        days_of_week=body.days_of_week or [],
        auto_create=body.auto_create,
        default_shift_type=body.default_shift_type,
        priority_level=body.priority_level,
        is_active=True,
    )
    db.add(tmpl)
    await db.commit()
    await db.refresh(tmpl)
    return TemplateBrief.model_validate(tmpl)


@router.patch("/templates/{template_id}", response_model=TemplateBrief)
async def update_template(
    template_id: int,
    body: UpdateTemplateBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    result = await db.execute(select(ShiftTemplate).where(ShiftTemplate.id == template_id))
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(tmpl, field, value)

    await db.commit()
    await db.refresh(tmpl)
    return TemplateBrief.model_validate(tmpl)


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    result = await db.execute(select(ShiftTemplate).where(ShiftTemplate.id == template_id))
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    # Soft-delete
    tmpl.is_active = False
    await db.commit()
    return {"message": "deleted"}


@router.post("/from-template", response_model=list[ShiftDetail], status_code=201)
async def create_from_template(
    body: CreateFromTemplateBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    result = await db.execute(
        select(ShiftTemplate).where(ShiftTemplate.id == body.template_id, ShiftTemplate.is_active == True)  # noqa: E712
    )
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

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
    users_map: dict[int, User] = {}
    u_res = await db.execute(select(User).where(User.id.in_(user_ids)))
    for u in u_res.scalars().all():
        users_map[u.id] = u
    missing = [uid for uid in user_ids if uid not in users_map]
    if missing:
        raise HTTPException(status_code=404, detail=f"Users not found: {missing}")

    created_shifts = []
    for uid in user_ids:
        shift = Shift(
            user_id=uid,
            start_time=start_dt,
            end_time=end_dt,
            status="planned",
            shift_type=tmpl.default_shift_type,
            max_requests=tmpl.default_max_requests,
            priority_level=tmpl.priority_level,
            shift_template_id=tmpl.id,
            specialization_focus=tmpl.required_specializations,
            current_request_count=0,
            completed_requests=0,
        )
        db.add(shift)
        await db.flush()
        created_shifts.append(shift)

    await db.commit()
    for s in created_shifts:
        await db.refresh(s)

    return [_shift_detail(s, users_map.get(s.user_id) if s.user_id else None) for s in created_shifts]


@router.post("/transfers/{transfer_id}/handle", response_model=TransferOut)
async def handle_transfer(
    transfer_id: int,
    body: HandleTransferBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    result = await db.execute(
        select(ShiftTransfer).where(ShiftTransfer.id == transfer_id).with_for_update()
    )
    transfer = result.scalar_one_or_none()
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
        exec_res = await db.execute(select(User).where(User.id == body.to_executor_id))
        new_executor = exec_res.scalar_one_or_none()
        if not new_executor:
            raise HTTPException(status_code=404, detail="Executor not found")
        has_exec_role = "executor" in _parse_user_roles(new_executor)
        if not has_exec_role:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Target user does not have executor role",
            )
        transfer.status = "assigned"
        transfer.to_executor_id = body.to_executor_id
        transfer.assigned_at = datetime.now(timezone.utc)

        # Actually reassign the shift to the new executor
        shift_result = await db.execute(
            select(Shift).where(Shift.id == transfer.shift_id).with_for_update()
        )
        the_shift = shift_result.scalar_one_or_none()
        if the_shift:
            the_shift.user_id = body.to_executor_id

    elif action == "reject":
        if transfer.status != "assigned":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot reject transfer in status '{transfer.status}' — expected 'assigned'",
            )
        transfer.status = "rejected"
        # Restore original executor on the shift
        shift_result = await db.execute(
            select(Shift).where(Shift.id == transfer.shift_id).with_for_update()
        )
        the_shift = shift_result.scalar_one_or_none()
        if the_shift:
            the_shift.user_id = transfer.from_executor_id
        else:
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
        transfer.status = "cancelled"

    await db.commit()
    await db.refresh(transfer)

    # Resolve executor names
    from_user_result = await db.execute(select(User).where(User.id == transfer.from_executor_id))
    from_user = from_user_result.scalar_one_or_none()

    to_user = None
    if transfer.to_executor_id:
        to_user_result = await db.execute(select(User).where(User.id == transfer.to_executor_id))
        to_user = to_user_result.scalar_one_or_none()

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
    result = await db.execute(select(Shift).where(Shift.id == shift_id))
    shift = result.scalar_one_or_none()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    user_obj = None
    if shift.user_id:
        u_result = await db.execute(select(User).where(User.id == shift.user_id))
        user_obj = u_result.scalar_one_or_none()

    return _shift_detail(shift, user_obj)


@router.post("", response_model=ShiftDetail, status_code=201)
async def create_shift(
    body: CreateShiftBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    # Validate executor exists and has executor role
    u_result = await db.execute(select(User).where(User.id == body.user_id))
    emp = u_result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="User not found")

    has_executor_role = "executor" in _parse_user_roles(emp)
    if not has_executor_role:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="User does not have executor role",
        )

    # Check for overlapping active or planned shifts
    overlap_result = await db.execute(
        select(Shift).where(
            Shift.user_id == body.user_id,
            Shift.status.in_(["active", "planned"]),
            Shift.start_time < body.end_time,
            Shift.end_time > body.start_time,
        ).with_for_update()
    )
    if overlap_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already has an active shift overlapping with the requested time range",
        )

    shift = Shift(
        user_id=body.user_id,
        start_time=body.start_time,
        end_time=body.end_time,
        status="active",
        shift_type=body.shift_type,
        specialization_focus=body.specialization_focus or [],
        max_requests=body.max_requests,
        priority_level=body.priority_level,
        notes=body.notes,
        current_request_count=0,
        completed_requests=0,
    )
    db.add(shift)
    await db.commit()
    await db.refresh(shift)

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
    result = await db.execute(select(Shift).where(Shift.id == shift_id))
    shift = result.scalar_one_or_none()
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
        u_res = await db.execute(select(User).where(User.id == body.user_id))
        new_user = u_res.scalar_one_or_none()
        if not new_user:
            raise HTTPException(status_code=404, detail="Target user not found")
        if "executor" not in _parse_user_roles(new_user):
            raise HTTPException(status_code=422, detail="Target user does not have executor role")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(shift, field, value)

    await db.commit()
    await db.refresh(shift)

    user_obj = None
    if shift.user_id:
        u_result = await db.execute(select(User).where(User.id == shift.user_id))
        user_obj = u_result.scalar_one_or_none()

    detail = _shift_detail(shift, user_obj)
    await publish_shift_event("shift.updated", detail.model_dump(mode="json"))
    return detail


@router.delete("/{shift_id}")
async def delete_shift(
    shift_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    result = await db.execute(select(Shift).where(Shift.id == shift_id))
    shift = result.scalar_one_or_none()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    if shift.status != "planned":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only planned shifts can be deleted — current status is '{shift.status}'",
        )

    await db.delete(shift)
    await db.commit()
    return {"message": "deleted"}


@router.post("/{shift_id}/end", response_model=ShiftDetail)
async def end_shift(
    shift_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    result = await db.execute(select(Shift).where(Shift.id == shift_id))
    shift = result.scalar_one_or_none()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    if shift.status not in ("active", "paused"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot end shift with status '{shift.status}'",
        )

    shift.end_time = datetime.now(timezone.utc)
    shift.status = "completed"

    await db.commit()
    await db.refresh(shift)

    user_obj = None
    if shift.user_id:
        u_result = await db.execute(select(User).where(User.id == shift.user_id))
        user_obj = u_result.scalar_one_or_none()

    detail = _shift_detail(shift, user_obj)
    await publish_shift_event("shift.ended", detail.model_dump(mode="json"))
    return detail
