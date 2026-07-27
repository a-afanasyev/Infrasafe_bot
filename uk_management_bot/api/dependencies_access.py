"""Access control dependencies for TWA-safe API endpoints."""
import logging
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.shift import Shift
from uk_management_bot.services.request_access import has_request_access_async

logger = logging.getLogger(__name__)


async def check_request_access(
    request_number: str,
    db: AsyncSession,
    user: User,
) -> Request:
    """Check user has access to a specific request. Returns request or raises 403.

    Правила — канон `utils/request_access` (П5): менеджер, владелец,
    исполнитель (по `executor_id`, индивидуальному назначению либо групповому
    при активной смене), сосед по квартире на статусе «Исполнено».

    Здесь была четвёртая копия этих правил, и она молча теряла ГРУППОВОЕ
    назначение: у групповых строк `RequestAssignment.executor_id` — NULL, а
    запрос искал по `executor_id == user.id`. Из-за этого список API заявку
    показывал (там группа учитывалась), а открыть её исполнитель не мог — 403.
    """
    result = await db.execute(
        select(Request).where(Request.request_number == request_number)
    )
    request = result.scalar_one_or_none()
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    if await has_request_access_async(db, user, request):
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
