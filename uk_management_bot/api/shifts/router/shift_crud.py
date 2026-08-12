"""AUD5-ARCH-3 волна 8 (block-move из api/shifts/router.py): CRUD смен.

Catch-all маршруты /{shift_id}* и POST "" — регистрируются ПОСЛЕДНИМИ
(см. __init__.py), иначе перехватили бы статические пути.
Тела перенесены байт-в-байт.
"""
from datetime import timezone

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_roles, _parse_user_roles
from uk_management_bot.api.shifts import service
from uk_management_bot.api.shifts.schemas import (
    CreateShiftBody, ReassignShiftBody, ShiftDetail, UpdateShiftBody,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.services.redis_pubsub import publish_request_event, publish_shift_event

from ._helpers import _shift_detail
from ._router import router


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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="User does not have executor role",
        )

    # APIFE-11: serialize this user's shift mutations so the overlap check and the
    # insert are atomic against concurrent writers (FOR UPDATE alone can't lock an
    # empty slot). Held until the transaction commits.
    await service.lock_user_shift_scope(db, body.user_id)
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

    # REG-02: смена исполнителя через PATCH запрещена — она обходила перенос
    # активных заявок / аудит / спец-проверку / уведомления. Только через
    # POST /shifts/{id}/reassign (reassign-core).
    if body.user_id is not None and body.user_id != shift.user_id:
        raise HTTPException(
            status_code=422,
            detail="Смена исполнителя только через POST /shifts/{id}/reassign",
        )

    data = body.model_dump(exclude_unset=True)
    # user_id, даже равный текущему, не применяем через PATCH (no-op подстраховка).
    data.pop("user_id", None)

    # Content edits (anything other than a status transition) are only allowed
    # while the shift is still editable — not after it is completed/cancelled.
    EDITABLE_STATUSES = {"planned", "active", "paused"}
    content = {k: v for k, v in data.items() if k != "status"}
    if content and shift.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot edit a '{shift.status}' shift",
        )

    # AUD5-APIFE-4: incoming times are already UTC-coerced by CreateShiftBody/
    # UpdateShiftBody field_validator. The existing shift.start_time/end_time
    # fallback values, however, come straight from the DB — coerce those too
    # in case a naive value slipped through (e.g. sqlite doesn't round-trip
    # tzinfo), so this comparison never mixes naive and aware.
    new_start = data.get("start_time", shift.start_time)
    new_end = data.get("end_time", shift.end_time)
    if new_start is not None and new_start.tzinfo is None:
        new_start = new_start.replace(tzinfo=timezone.utc)
    if new_end is not None and new_end.tzinfo is None:
        new_end = new_end.replace(tzinfo=timezone.utc)
    if new_start is not None and new_end is not None and new_end <= new_start:
        raise HTTPException(status_code=422, detail="end_time must be after start_time")

    # Prevent double-booking when the time window or executor changes
    # (mirrors the overlap check in create_shift, excluding this shift itself).
    if ("start_time" in data or "end_time" in data or "user_id" in data) \
            and new_start is not None and new_end is not None:
        target_user_id = data.get("user_id", shift.user_id)
        # APIFE-11: advisory lock makes check-then-update atomic; lock=True also
        # row-locks any existing overlap (was lock=False — the odd one out).
        await service.lock_user_shift_scope(db, target_user_id)
        overlap = await service.find_overlapping_shift_for_update(
            db, user_id=target_user_id, start_time=new_start, end_time=new_end,
            exclude_shift_id=shift_id, lock=True,
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


@router.post("/{shift_id}/reassign", response_model=ShiftDetail)
async def reassign_shift(
    shift_id: int,
    body: ReassignShiftBody,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("manager")),
):
    """REG-02: прямой менеджерский reassign смены (без согласия получателя).

    Меняет владельца смены, переносит активные заявки старого исполнителя новому
    (status-preserving), пишет ShiftTransfer-историю. Realtime: `shift.updated` +
    `request.updated` на каждую перенесённую заявку.
    """
    res = await service.reassign_shift_web(
        db, shift_id=shift_id, new_executor_id=body.executor_id, manager_id=_user.id
    )
    if not res["success"]:
        err = res["error"]
        status_map = {
            "shift_not_found": 404,
            "executor_not_found": 404,
            "overlap": status.HTTP_409_CONFLICT,
        }
        raise HTTPException(status_code=status_map.get(err, status.HTTP_422_UNPROCESSABLE_CONTENT), detail=err)

    shift = res["shift"]
    user_obj = await service.get_user(db, shift.user_id) if shift.user_id else None
    detail = _shift_detail(shift, user_obj)
    await publish_shift_event("shift.updated", detail.model_dump(mode="json"))
    for number in res["moved_request_numbers"]:
        await publish_request_event("request.updated", {"number": number})
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
