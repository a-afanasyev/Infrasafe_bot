"""Access control dependencies for TWA-safe API endpoints."""
import logging
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from uk_management_bot.api.dependencies import _parse_user_roles
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.request_assignment import RequestAssignment
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment
from uk_management_bot.database.models.shift import Shift

logger = logging.getLogger(__name__)


async def check_request_access(
    request_number: str,
    db: AsyncSession,
    user: User,
) -> Request:
    """Check user has access to a specific request. Returns request or raises 403.

    Access rules:
    - Owner (request.user_id == user.id): always
    - Apartment resident: only if request.status == 'Исполнено' (acceptance flow)
    - Executor (via RequestAssignment OR request.executor_id fallback): always
    - Manager: always
    """
    result = await db.execute(
        select(Request).where(Request.request_number == request_number)
    )
    request = result.scalar_one_or_none()
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    roles = _parse_user_roles(user)

    # Manager — full access
    if "manager" in roles:
        return request

    # Owner — full access
    if request.user_id == user.id:
        return request

    # Executor — via RequestAssignment or executor_id fallback
    if "executor" in roles:
        if request.executor_id == user.id:
            return request
        assignment = await db.execute(
            select(RequestAssignment).where(
                RequestAssignment.request_number == request_number,
                RequestAssignment.executor_id == user.id,
                RequestAssignment.status == "active",
            )
        )
        if assignment.scalar_one_or_none():
            return request

    # Apartment resident — only for acceptance (status == Исполнено)
    if request.apartment_id and request.status == "Исполнено":
        resident = await db.execute(
            select(UserApartment).where(
                UserApartment.user_id == user.id,
                UserApartment.apartment_id == request.apartment_id,
                UserApartment.status == "approved",
            )
        )
        if resident.scalar_one_or_none():
            return request

    raise HTTPException(status_code=403, detail="Access denied")


async def require_active_shift(
    db: AsyncSession,
    user: User,
) -> Shift:
    """Require executor to have an active shift. Returns shift or raises 403."""
    result = await db.execute(
        select(Shift).where(
            Shift.user_id == user.id,
            Shift.status == "active",
        )
    )
    shift = result.scalars().first()  # .first() not scalar_one: executor may have multiple active shifts
    if not shift:
        raise HTTPException(
            status_code=403,
            detail="Active shift required. Start a shift first.",
        )
    return shift


def is_assigned_executor(request: Request, user: User, assignments: list) -> bool:
    """Check if user is assigned executor (via RequestAssignment OR executor_id fallback)."""
    if request.executor_id == user.id:
        return True
    return any(
        a.executor_id == user.id and a.status == "active"
        for a in assignments
    )
