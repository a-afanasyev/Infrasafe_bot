"""Адресаты жительских уведомлений: одобренные жители подъезда дома.

EXISTS вместо JOIN (образец ``services/residents/queries.py:_belonging_exists``):
пользователь с двумя квартирами в подъезде — одна строка.
"""

from __future__ import annotations

from dataclasses import dataclass

from collections.abc import Iterable

from sqlalchemy import Row, Select, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.user_apartment import (
    UserApartment,
    UserApartmentStatus,
)

from ._shared import DEFAULT_LANGUAGE

# Статус пользователя, при котором уведомления не шлём
USER_STATUS_BLOCKED = "blocked"


@dataclass(frozen=True)
class Recipient:
    """Кому слать: id пользователя, его Telegram-id и язык интерфейса."""

    user_id: int
    telegram_id: int
    language: str


def _residents_stmt(building_id: int, entrance_number: int) -> Select:
    belongs = exists(
        select(UserApartment.id)
        .join(Apartment, UserApartment.apartment_id == Apartment.id)
        .where(
            UserApartment.user_id == User.id,
            UserApartment.status == UserApartmentStatus.APPROVED.value,
            Apartment.building_id == building_id,
            Apartment.entrance == entrance_number,
            Apartment.is_active.is_(True),
        )
    )
    return (
        select(User.id, User.telegram_id, User.language)
        .where(
            belongs,
            User.deleted_at.is_(None),
            User.status != USER_STATUS_BLOCKED,
            User.bot_blocked_at.is_(None),
            User.telegram_id.is_not(None),
        )
        .order_by(User.id)
    )


def _to_recipients(rows: Iterable[Row]) -> list[Recipient]:
    return [
        Recipient(user_id=user_id, telegram_id=telegram_id, language=language or DEFAULT_LANGUAGE)
        for user_id, telegram_id, language in rows
    ]


def residents_of_entrance_sync(db: Session, building_id: int, entrance_number: int) -> list[Recipient]:
    """Одобренные жители подъезда, не удалённые, не заблокированные, с живым ботом."""
    return _to_recipients(db.execute(_residents_stmt(building_id, entrance_number)).all())


async def residents_of_entrance_async(
    db: AsyncSession, building_id: int, entrance_number: int
) -> list[Recipient]:
    """Async-зеркало ``residents_of_entrance_sync``."""
    rows = (await db.execute(_residents_stmt(building_id, entrance_number))).all()
    return _to_recipients(rows)
