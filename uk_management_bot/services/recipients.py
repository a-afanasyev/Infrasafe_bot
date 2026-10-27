"""Адресаты уведомлений: DTO получателя и выборка «у кого есть действие».

Получатель — одобренный, не удалённый пользователь с живым ботом
(`bot_blocked_at IS NULL`, есть `telegram_id`). Кому слать решает действие
каталога (authz), а не имя роли: переопределения из админки ролей учитываются.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import Row, Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from uk_management_bot.authz import get_action
from uk_management_bot.database.models.user import User
from uk_management_bot.database.roles_type import roles_contain

DEFAULT_LANGUAGE = "ru"


@dataclass(frozen=True)
class Recipient:
    """Кому слать: id пользователя, его Telegram-id и язык интерфейса."""

    user_id: int
    telegram_id: int
    language: str


def to_recipients(rows: Iterable[Row]) -> list[Recipient]:
    return [
        Recipient(user_id=user_id, telegram_id=telegram_id, language=language or DEFAULT_LANGUAGE)
        for user_id, telegram_id, language in rows
    ]


def _with_action_stmt(action_key: str) -> Optional[Select]:
    roles = sorted(get_action(action_key).roles)
    if not roles:
        # Действие никому не выдано — никому и не шлём (не «всем»).
        return None
    return (
        select(User.id, User.telegram_id, User.language)
        .where(
            roles_contain(User.roles, *roles),
            User.status == "approved",
            User.deleted_at.is_(None),
            User.bot_blocked_at.is_(None),
            User.telegram_id.is_not(None),
        )
        .order_by(User.id)
    )


def recipients_with_action_sync(db: Session, action_key: str) -> list[Recipient]:
    """Одобренные пользователи с живым ботом, которым разрешено действие."""
    stmt = _with_action_stmt(action_key)
    return [] if stmt is None else to_recipients(db.execute(stmt).all())


async def recipients_with_action_async(db: AsyncSession, action_key: str) -> list[Recipient]:
    """Async-зеркало ``recipients_with_action_sync``."""
    stmt = _with_action_stmt(action_key)
    return [] if stmt is None else to_recipients((await db.execute(stmt)).all())
