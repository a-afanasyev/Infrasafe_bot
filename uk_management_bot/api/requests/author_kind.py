"""От кого заявка: ``resident`` / ``staff`` / ``system`` — для подписи на карточке.

Отдельной колонки нет: признак выводится из того, что заявка уже хранит
(канал, кто доложил, режим приёмки). Звонок жителя, записанный диспетчером,
остаётся заявкой жителя; заявка диспетчера «от себя» (владелец — сам сотрудник)
— заявкой сотрудника.
"""
from __future__ import annotations

from typing import Iterable, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.user import User
from uk_management_bot.utils.auth_helpers import parse_roles_safe
from uk_management_bot.utils.constants import ACCEPTANCE_MODE_MANAGER, ROLE_APPLICANT

RESIDENT, STAFF, SYSTEM = "resident", "staff", "system"
_CALL_CENTER = "call_center"


def author_kind(req, owner_roles: Mapping[int, list[str]]) -> str:
    """``owner_roles`` — роли владельцев заявок колл-центра (см. ``load_owner_roles``)."""
    if req.source == "infrasafe":
        return SYSTEM
    if (req.source == "inspector" or req.reported_by_user_id is not None
            or req.acceptance_mode == ACCEPTANCE_MODE_MANAGER):
        return STAFF
    if req.source == _CALL_CENTER:
        roles = owner_roles.get(req.user_id)
        if roles and ROLE_APPLICANT not in roles:
            return STAFF
    return RESIDENT


async def load_owner_roles(db: AsyncSession, reqs: Iterable) -> dict[int, list[str]]:
    """Роли владельцев заявок колл-центра одним запросом; остальным заявкам они не нужны."""
    owner_ids = {r.user_id for r in reqs if r.source == _CALL_CENTER}
    if not owner_ids:
        return {}
    rows = await db.execute(select(User.id, User.roles).where(User.id.in_(owner_ids)))
    return {uid: parse_roles_safe(roles) for uid, roles in rows.all()}
