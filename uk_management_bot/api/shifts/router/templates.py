"""AUD5-ARCH-3 волна 8 (block-move из api/shifts/router.py): шаблоны смен.

CRUD /templates* + POST /from-template. Тела перенесены байт-в-байт.
"""
from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.shifts import service
from uk_management_bot.api.shifts.schemas import (
    CreateFromTemplateBody, CreateTemplateBody, ShiftDetail,
    TemplateBrief, UpdateTemplateBody,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.business_time import business_wall_clock

from ._helpers import _shift_detail
from ._router import router


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

    # ARCH-135(б): часы шаблона — стенка бизнес-зоны, та же семантика, что у
    # бот-пути (shift_planning_service._create_single_shift_from_template);
    # прямой datetime(..., tzinfo=utc) давал рассинхрон путей на офсет зоны.
    start_dt = business_wall_clock(target_date, tmpl.start_hour, tmpl.start_minute or 0)
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

    try:
        created_shifts = await service.create_shifts_from_template(
            db, tmpl=tmpl, user_ids=user_ids, start_dt=start_dt, end_dt=end_dt
        )
    except service.ShiftOverlapError as exc:
        # APIFE-5: all-or-nothing — any overlapping user aborts the whole batch.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Overlapping shifts for users: {exc.conflicts}",
        )

    return [_shift_detail(s, users_map.get(s.user_id) if s.user_id else None) for s in created_shifts]
