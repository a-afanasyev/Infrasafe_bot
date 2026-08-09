"""Сервис-слой профиля (AUD5-ARCH-2 волна 2, ARCH-05a-канон).

Module-level async функции `(db, *, plain-параметры) -> ORM|примитивы`.
Валидация ввода (языки, роли), HTTPException и схемы — в router.py.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.user import User


async def apply_profile_update(
    db: AsyncSession,
    user_id: int,
    *,
    language: Optional[str] = None,
    email: Optional[str] = None,
) -> None:
    """Обновляет language/email пользователя (только не-None поля) и коммитит."""
    result = await db.execute(select(User).where(User.id == user_id))
    db_user = result.scalar_one()
    if language is not None:
        db_user.language = language
    if email is not None:
        db_user.email = email
    await db.commit()


async def set_active_role(db: AsyncSession, user_id: int, *, active_role: str) -> None:
    """Ставит active_role (принадлежность роли проверяет роутер) и коммитит."""
    result = await db.execute(select(User).where(User.id == user_id))
    db_user = result.scalar_one()
    db_user.active_role = active_role
    await db.commit()


async def approved_apartment_rows(db: AsyncSession, user_id: int):
    """Approved-квартиры пользователя с активной цепочкой квартира→дом→двор."""
    from uk_management_bot.database.models.user_apartment import UserApartment
    from uk_management_bot.database.models.apartment import Apartment
    from uk_management_bot.database.models.building import Building
    from uk_management_bot.database.models.yard import Yard

    result = await db.execute(
        select(Apartment, Building.address, Yard.name)
        .join(UserApartment, UserApartment.apartment_id == Apartment.id)
        .join(Building, Apartment.building_id == Building.id)
        .join(Yard, Building.yard_id == Yard.id)
        .where(
            UserApartment.user_id == user_id,
            UserApartment.status == "approved",
            # Активная цепочка квартира→дом→двор (план «Обходчик»).
            Apartment.is_active.is_(True),
            Building.is_active.is_(True),
            Yard.is_active.is_(True),
        )
    )
    return result.all()
