from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.database.models.user import User

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ShiftOut(BaseModel):
    id: int
    user_id: Optional[int]
    start_time: Optional[str]
    end_time: Optional[str]
    status: str
    notes: Optional[str]

    class Config:
        from_attributes = True


class StartShiftBody(BaseModel):
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _shift_out(shift: Shift) -> ShiftOut:
    return ShiftOut(
        id=shift.id,
        user_id=shift.user_id,
        start_time=shift.start_time.isoformat() if shift.start_time else None,
        end_time=shift.end_time.isoformat() if shift.end_time else None,
        status=shift.status,
        notes=shift.notes,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/current", response_model=Optional[ShiftOut])
async def get_current_shift(
    user: User = Depends(require_roles("executor")),
    db: AsyncSession = Depends(get_db),
):
    """Returns the current active shift for the authenticated executor, or null."""
    result = await db.execute(
        select(Shift).where(Shift.user_id == user.id, Shift.status == "active")
    )
    shift = result.scalar_one_or_none()
    if shift is None:
        return None
    return _shift_out(shift)


@router.get("/me", response_model=list[ShiftOut])
async def get_my_shifts(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_roles("executor")),
    db: AsyncSession = Depends(get_db),
):
    """Returns list of the authenticated executor's shifts (all statuses), ordered by start_time desc."""
    result = await db.execute(
        select(Shift)
        .where(Shift.user_id == user.id)
        .order_by(Shift.start_time.desc())
        .limit(limit)
    )
    shifts = result.scalars().all()
    return [_shift_out(s) for s in shifts]


@router.post("/start", response_model=ShiftOut, status_code=status.HTTP_201_CREATED)
async def start_shift(
    body: StartShiftBody,
    user: User = Depends(require_roles("executor")),
    db: AsyncSession = Depends(get_db),
):
    """Creates a new active shift for the authenticated executor."""
    now = datetime.now(timezone.utc)
    shift = Shift(
        user_id=user.id,
        status="active",
        start_time=now,
        notes=body.notes,
    )
    db.add(shift)
    await db.commit()
    await db.refresh(shift)
    return _shift_out(shift)


@router.post("/{shift_id}/end", response_model=ShiftOut)
async def end_shift(
    shift_id: int,
    user: User = Depends(require_roles("executor")),
    db: AsyncSession = Depends(get_db),
):
    """Ends a specific active shift belonging to the authenticated executor."""
    result = await db.execute(select(Shift).where(Shift.id == shift_id))
    shift = result.scalar_one_or_none()

    if shift is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift not found")
    if shift.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your shift")
    if shift.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Shift is not active (current status: {shift.status})",
        )

    shift.end_time = datetime.now(timezone.utc)
    shift.status = "completed"
    await db.commit()
    await db.refresh(shift)
    return _shift_out(shift)
