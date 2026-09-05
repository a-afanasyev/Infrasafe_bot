"""Точечные выборки API-слоя «Лифты», не принадлежащие домену лифтов.

Имена дворов и пользователей для обогащения карточек (одним запросом на
страницу), проверка права жителя на дом (одобренная квартира в нём).
"""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import UserApartment, UserApartmentStatus
from uk_management_bot.database.models.yard import Yard


async def yard_names_by_ids(db: AsyncSession, yard_ids: Iterable[int]) -> dict[int, str]:
    """``{yard_id: name}`` для набора дворов (пустой набор — без запроса)."""
    ids = sorted({int(yard_id) for yard_id in yard_ids})
    if not ids:
        return {}
    rows = (await db.execute(select(Yard.id, Yard.name).where(Yard.id.in_(ids)))).all()
    return {int(yard_id): name for yard_id, name in rows}


async def users_by_ids(db: AsyncSession, user_ids: Iterable[int | None]) -> dict[int, User]:
    """``{user_id: User}`` для имён исполнителя/заявителя в строках заявок."""
    ids = sorted({int(user_id) for user_id in user_ids if user_id is not None})
    if not ids:
        return {}
    rows = (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    return {user.id: user for user in rows}


async def has_approved_apartment_in_building(
    db: AsyncSession, user_id: int, building_id: int
) -> bool:
    """Есть ли у пользователя одобренная связь с квартирой этого дома."""
    stmt = select(
        exists().where(
            UserApartment.user_id == user_id,
            UserApartment.status == UserApartmentStatus.APPROVED.value,
            UserApartment.apartment_id == Apartment.id,
            Apartment.building_id == building_id,
        )
    )
    return bool((await db.execute(stmt)).scalar())
