"""Async data-access хелперы для повторяющихся user-lookup'ов (ARC-06 PR2).

SSOT для запроса пользователя по telegram_id / id в API-слое: до этого одна и
та же `select(User).where(...)` дублировалась 5× (telegram_id) + 4× (id) по
роутерам auth/registration и dependencies.

⚠ Парные варианты по scalar-методу (сохранение поведения вызывающих):
  • get_*   → scalar_one_or_none() — None, если пользователя нет;
  • require_* → scalar_one() — бросает NoResultFound/MultipleResultsFound.
None-проверка / raise HTTPException / status-branching остаются у вызывающего.

AST-гейт `tests/api/test_arc06_user_lookup_gate.py` запрещает инлайн
`select(User).where(User.id/telegram_id == ...)` в мигрированных файлах.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.user import User


async def get_user_by_telegram_id(db: AsyncSession, telegram_id: int) -> Optional[User]:
    """Пользователь по telegram_id или None."""
    return (
        await db.execute(select(User).where(User.telegram_id == telegram_id))
    ).scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    """Пользователь по id или None."""
    return (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()


async def require_user_by_telegram_id(db: AsyncSession, telegram_id: int) -> User:
    """Пользователь по telegram_id; бросает, если нет/несколько (инвариант вызова)."""
    return (
        await db.execute(select(User).where(User.telegram_id == telegram_id))
    ).scalar_one()


async def require_user_by_id(db: AsyncSession, user_id: int) -> User:
    """Пользователь по id; бросает, если нет/несколько (инвариант вызова)."""
    return (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one()
