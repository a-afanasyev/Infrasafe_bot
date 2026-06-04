"""Сервис обратной связи (жалобы / пожелания).

Содержит создание обращения (sync — для бота), перечисление менеджеров для
уведомлений (раздельно для sync `Session` бота и `AsyncSession` API), и
построение текста уведомления менеджерам. Доставка в Telegram — в
``notification_service`` (`deliver_feedback_to_managers`).
"""
from __future__ import annotations

import html
import logging

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from uk_management_bot.database.models.feedback import Feedback
from uk_management_bot.database.models.user import User
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

# Менеджеры: новый JSON-формат roles ИЛИ legacy одиночное поле role; только
# активные (не удалённые, одобренные).
_MANAGER_FILTER = or_(User.roles.like('%"manager"%'), User.role == "manager")
_ACTIVE_FILTER = and_(User.deleted_at.is_(None), User.status == "approved")

# Лимиты Telegram
_CAPTION_LIMIT = 1024
_MESSAGE_LIMIT = 4096

FEEDBACK_TYPES = ("complaint", "wish")


def create_feedback_sync(
    db: Session,
    *,
    user_id: int,
    type_: str,
    text: str,
    media_files: list[int] | None = None,
    source: str = "bot",
) -> Feedback:
    """Создаёт обращение (sync-сессия, путь бота)."""
    fb = Feedback(
        user_id=user_id,
        type=type_,
        text=text,
        media_files=list(media_files) if media_files else [],
        source=source,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


def manager_telegram_ids_sync(db: Session) -> list[int]:
    rows = db.query(User).filter(_MANAGER_FILTER, _ACTIVE_FILTER).all()
    return [u.telegram_id for u in rows if u.telegram_id]


async def manager_telegram_ids_async(db) -> list[int]:  # db: AsyncSession

    res = await db.execute(select(User).where(_MANAGER_FILTER, _ACTIVE_FILTER))
    return [u.telegram_id for u in res.scalars().all() if u.telegram_id]


def _type_label(type_: str, lang: str = "ru") -> str:
    key = "feedback.type_complaint" if type_ == "complaint" else "feedback.type_wish"
    return get_text(key, language=lang)


def build_manager_notify_text(
    *, type_: str, text: str, author_name: str | None, has_photo: bool, lang: str = "ru"
) -> str:
    """HTML-текст уведомления менеджерам. Экранирует пользовательский ввод.

    Обрезает под лимит caption (фото) / message (без фото), чтобы Telegram не
    отверг сообщение.
    """
    label = html.escape(_type_label(type_, lang))
    author = html.escape(author_name or "—")
    header = f"📨 <b>{label}</b>\n👤 {author}\n\n"
    limit = (_CAPTION_LIMIT if has_photo else _MESSAGE_LIMIT) - len(header) - 1
    # Обрезаем СЫРОЙ текст до escape, иначе можно разрезать HTML-сущность (&amp; → &amp).
    if len(text) > limit:
        text = text[: max(0, limit - 1)] + "…"
    return header + html.escape(text)
