from datetime import datetime, timezone, date as date_type
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import aliased

from uk_management_bot.api.dependencies import get_db, get_current_user, require_roles
from uk_management_bot.api.shifts.schemas import (
    EmployeeBrief, EmployeeDetail,
    ShiftBrief, ShiftDetail,
    TransferOut, ShiftStatsOut,
    CreateShiftBody, UpdateShiftBody,
    CreateFromTemplateBody, HandleTransferBody,
    TemplateBrief, CreateTemplateBody, UpdateTemplateBody,
)
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.shift_template import ShiftTemplate
from uk_management_bot.database.models.shift_transfer import ShiftTransfer
from uk_management_bot.database.models.user import User
from uk_management_bot.services.redis_pubsub import publish_request_event  # will add publish_shift_event later

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("manager")),
):
    query = select(User).where(
        or_(
            User.role == "executor",
            User.roles.like('%executor%'),
        )
    )

    if specialization:
        query = query.where(User.specialization.like(f'%{specialization}%'))

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
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
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
        dt_from = datetime.fromisoformat(date_from)
        query = query.where(Shift.start_time >= dt_from)
    if date_to:
        dt_to = datetime.fromisoformat(date_to)
        query = query.where(Shift.start_time <= dt_to)

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
    date_from: str = Query(...),
    date_to: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    dt_from = datetime.fromisoformat(date_from)
    dt_to = datetime.fromisoformat(date_to)

    result = await db.execute(
        select(Shift)
        .where(Shift.start_time >= dt_from, Shift.start_time <= dt_to)
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
                User.roles.like('%executor%'),
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
    offset: int = Query(0),
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
    offset: int = Query(0),
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

    for field, value in body.model_dump(exclude_none=True).items():
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

    user_ids = body.user_ids or [None]
    created_shifts = []
    for uid in user_ids:
        if uid is not None:
            user_check = await db.execute(select(User).where(User.id == uid))
            emp = user_check.scalar_one_or_none()
            if not emp:
                raise HTTPException(status_code=404, detail=f"User {uid} not found")

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

    details = []
    for s in created_shifts:
        await db.refresh(s)
        user_obj = None
        if s.user_id:
            u_res = await db.execute(select(User).where(User.id == s.user_id))
            user_obj = u_res.scalar_one_or_none()
        details.append(_shift_detail(s, user_obj))

    return details


@router.post("/transfers/{transfer_id}/handle", response_model=TransferOut)
async def handle_transfer(
    transfer_id: int,
    body: HandleTransferBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    result = await db.execute(
        select(ShiftTransfer).where(ShiftTransfer.id == transfer_id)
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
        transfer.status = "assigned"
        transfer.to_executor_id = body.to_executor_id
        transfer.assigned_at = datetime.now(timezone.utc)

    elif action == "reject":
        if transfer.status != "assigned":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot reject transfer in status '{transfer.status}' — expected 'assigned'",
            )
        transfer.status = "rejected"

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

    await publish_request_event("transfer.updated", transfer_out.model_dump(mode="json"))
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

    has_executor_role = (emp.role == "executor") or (emp.roles and "executor" in emp.roles)
    if not has_executor_role:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="User does not have executor role",
        )

    # Check for overlapping active shifts
    overlap_result = await db.execute(
        select(Shift).where(
            Shift.user_id == body.user_id,
            Shift.status == "active",
            Shift.start_time < body.end_time,
            Shift.end_time > body.start_time,
        )
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
    await publish_request_event("shift.created", detail.model_dump(mode="json"))
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

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(shift, field, value)

    await db.commit()
    await db.refresh(shift)

    user_obj = None
    if shift.user_id:
        u_result = await db.execute(select(User).where(User.id == shift.user_id))
        user_obj = u_result.scalar_one_or_none()

    detail = _shift_detail(shift, user_obj)
    await publish_request_event("shift.updated", detail.model_dump(mode="json"))
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

    shift.end_time = datetime.now(timezone.utc)
    shift.status = "completed"

    await db.commit()
    await db.refresh(shift)

    user_obj = None
    if shift.user_id:
        u_result = await db.execute(select(User).where(User.id == shift.user_id))
        user_obj = u_result.scalar_one_or_none()

    detail = _shift_detail(shift, user_obj)
    await publish_request_event("shift.ended", detail.model_dump(mode="json"))
    return detail
