"""GET /api/v2/requests/{n}/handover-candidates — кому инженер передаёт заявку.

Инженер разбирает «Инженерный разбор» и передаёт работу мастеру любой
специализации, поэтому кандидаты — ВСЕ одобренные исполнители (подбор по
категории здесь неверен: engineering → repair дал бы одних разнорабочих).
Сама передача — существующий `PATCH /{n} {executor_id}` (MANAGER_ASSIGN; гвард
пускает инженера только на engineering). Путь под заявленным edge-префиксом.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_action
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.user import User
from uk_management_bot.database.roles_type import roles_contain
from uk_management_bot.services.auto_manager.rule_engine import OPEN_LOAD_STATUSES
from uk_management_bot.utils.categories import is_engineering_category
from uk_management_bot.utils.specializations import matches_required_specs, parse_specializations
from uk_management_bot.utils.user_names import display_name
from uk_management_bot.utils.workflow_predicates import status_in_clause

router = APIRouter()


class HandoverCandidate(BaseModel):
    id: int
    name: str
    specializations: list[str]
    open_requests: int


@router.get("/{request_number}/handover-candidates", response_model=list[HandoverCandidate])
async def handover_candidates(
    request_number: str,
    specialization: Optional[str] = Query(None, max_length=64),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_action("requests.engineering")),
):
    """Одобренные исполнители со специализациями и открытой нагрузкой, кроме
    текущего исполнителя; `?specialization=` — только покрывающие её."""
    req = (await db.execute(
        select(Request.category, Request.executor_id)
        .where(Request.request_number == request_number))).first()
    # Один ответ на «нет» и «не инженерная» — код не выдаёт категорию чужой заявки.
    if req is None or not is_engineering_category(req.category):
        raise HTTPException(status_code=404, detail="Request not found")

    users = (await db.execute(
        select(User).where(
            roles_contain(User.roles, "executor"),
            User.status == "approved",
            User.deleted_at.is_(None),
        ).order_by(User.id))).scalars().all()
    candidates = [
        u for u in users
        if u.id != req.executor_id
        and (specialization is None
             or matches_required_specs(parse_specializations(u), {specialization}))
    ]
    load = dict((await db.execute(
        select(Request.executor_id, func.count())
        .where(Request.executor_id.in_([u.id for u in candidates]),
               status_in_clause(OPEN_LOAD_STATUSES))
        .group_by(Request.executor_id))).all()) if candidates else {}
    return [
        HandoverCandidate(id=u.id, name=display_name(u), open_requests=load.get(u.id, 0),
                          specializations=sorted(parse_specializations(u)))
        for u in candidates
    ]
