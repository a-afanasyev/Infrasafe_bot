"""SSOT-кластер #1, PR2d — резолвер seeded system-user.

SYSTEM-операции (авто-диспетчер, оптимизатор назначений) не имеют человека-
актора, но `RequestAssignment.created_by` / `request.assigned_by` — FK на
users.id. Переиспользуем уже засеянного system-user'а (InfraSafe, миграция
009_seed_infrasafe_system_user, telegram_id=settings.INFRASAFE_SYSTEM_USER_
TELEGRAM_ID) как created_by/assigned_by. «Кто именно» (dispatcher/inbound/…)
фиксируется принципалом в audit_logs независимо от этого id.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.user import User


class SystemUserMissing(RuntimeError):
    """Seeded system-user отсутствует (не применена миграция 009)."""


_MSG = ("System user not found — apply migration 009_seed_infrasafe_system_user "
        "(users.telegram_id == settings.INFRASAFE_SYSTEM_USER_TELEGRAM_ID)")


def get_system_user_id_sync(db: Session) -> int:
    uid = (db.query(User.id)
           .filter(User.telegram_id == settings.INFRASAFE_SYSTEM_USER_TELEGRAM_ID)
           .scalar())
    if uid is None:
        raise SystemUserMissing(_MSG)
    return uid


async def get_system_user_id_async(db: AsyncSession) -> int:
    uid = await db.scalar(
        select(User.id).where(
            User.telegram_id == settings.INFRASAFE_SYSTEM_USER_TELEGRAM_ID))
    if uid is None:
        raise SystemUserMissing(_MSG)
    return uid
