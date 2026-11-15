"""Адресаты рассылки записи ``notices``: все жители, дворы или дома.

Житель относится к дому/двору, если у него есть одобренная привязка к
действующей квартире в нём (тот же критерий, что у уведомлений по лифтам —
``services/elevator_service/recipients.py``). Общие условия «кому вообще
можно писать» (житель, одобрен, не удалён, бот не заблокирован) добавляет
воркер рассылки.
"""
from __future__ import annotations

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.notice import NOTICE_SCOPE_ALL, NOTICE_SCOPE_BUILDINGS, NOTICE_SCOPE_YARDS
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment, UserApartmentStatus
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.database.roles_type import roles_contain


def audience_clause(scope: str, scope_ids: list[int]) -> tuple:
    """Условия на ``User`` для адресатов; для «всех» — пусто."""
    if scope == NOTICE_SCOPE_ALL:
        return ()
    lives = (
        select(UserApartment.id)
        .join(Apartment, UserApartment.apartment_id == Apartment.id)
        .where(
            UserApartment.user_id == User.id,
            UserApartment.status == UserApartmentStatus.APPROVED.value,
            Apartment.is_active.is_(True),
        )
    )
    if scope == NOTICE_SCOPE_BUILDINGS:
        lives = lives.where(Apartment.building_id.in_(scope_ids))
    else:
        lives = lives.join(Building, Apartment.building_id == Building.id).where(Building.yard_id.in_(scope_ids))
    return (exists(lives),)


def eligible_clause() -> tuple:
    """Кому можно писать — те же условия, что у воркера рассылки."""
    return (roles_contain(User.roles, "applicant"), User.status == "approved",
            User.deleted_at.is_(None), User.bot_blocked_at.is_(None), User.telegram_id.is_not(None))


async def count_recipients(db: AsyncSession, scope: str, scope_ids: list[int]) -> int:
    stmt = select(func.count()).select_from(User).where(*eligible_clause(), *audience_clause(scope, scope_ids))
    return int((await db.execute(stmt)).scalar_one())


async def unknown_scope_ids(db: AsyncSession, scope: str, scope_ids: list[int]) -> list[int]:
    """Идентификаторы, которых нет среди действующих дворов/домов справочника."""
    if scope == NOTICE_SCOPE_ALL or not scope_ids:
        return []
    model = Yard if scope == NOTICE_SCOPE_YARDS else Building
    rows = await db.execute(select(model.id).where(model.id.in_(scope_ids), model.is_active.is_(True)))
    known = {int(r) for r in rows.scalars().all()}
    return sorted(set(scope_ids) - known)
