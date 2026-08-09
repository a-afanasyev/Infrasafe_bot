"""Сервис-слой обратной связи (AUD5-ARCH-2 волна 3, ARC-05a-канон).

Module-level async функции `(db, *, plain-параметры) -> ORM|примитивы`.
Валидация ввода, переходы статусов, HTTPException, media-proxy и
Telegram-уведомления — в router.py.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.users.queries import get_user_by_id
from uk_management_bot.database.models.feedback import Feedback
from uk_management_bot.database.models.user import User


async def persist_feedback(
    db: AsyncSession, *, user_id: int, feedback_type: str, text: str, source: str = "twa"
) -> Feedback:
    fb = Feedback(user_id=user_id, type=feedback_type, text=text, media_files=[], source=source)
    db.add(fb)
    await db.commit()
    await db.refresh(fb)
    return fb


async def attach_media(db: AsyncSession, feedback: Feedback, *, media_ids: list) -> None:
    """Привязывает загруженные вложения (id из media-service) и коммитит."""
    feedback.media_files = media_ids
    await db.commit()


async def feedback_page(
    db: AsyncSession,
    *,
    feedback_type: Optional[str],
    status: Optional[str],
    limit: int,
    offset: int,
):
    """→ (rows, total); rows — пары (Feedback, User-автор).

    count и rows используют ОДИН и тот же inner-join, иначе пагинация разъедется,
    если у обращения user_id ссылается на отсутствующего пользователя.
    """
    conds = []
    if feedback_type:
        conds.append(Feedback.type == feedback_type)
    if status:
        conds.append(Feedback.status == status)

    total = (
        await db.execute(
            select(func.count(Feedback.id)).join(User, Feedback.user_id == User.id).where(*conds)
        )
    ).scalar() or 0
    rows = (
        await db.execute(
            select(Feedback, User)
            .join(User, Feedback.user_id == User.id)
            .where(*conds)
            .order_by(Feedback.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return rows, total


async def feedback_by_id(db: AsyncSession, fid: int) -> Optional[Feedback]:
    return (await db.execute(select(Feedback).where(Feedback.id == fid))).scalar_one_or_none()


async def author_of(db: AsyncSession, user_id: int) -> Optional[User]:
    return await get_user_by_id(db, user_id)


async def apply_feedback_edits(
    db: AsyncSession,
    feedback: Feedback,
    *,
    status: Optional[str] = None,
    reply: Optional[str] = None,
    replied_by: Optional[int] = None,
) -> None:
    """Применяет уже ПРОВАЛИДИРОВАННЫЕ роутером изменения и коммитит.

    status/reply = None — поле не меняется; при новом reply проставляются
    replied_at (UTC now) и replied_by.
    """
    if status is not None:
        feedback.status = status
    if reply is not None:
        feedback.reply = reply
        feedback.replied_at = datetime.now(timezone.utc)
        feedback.replied_by = replied_by
    await db.commit()
    await db.refresh(feedback)
