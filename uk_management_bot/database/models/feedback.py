"""
Модель обратной связи (жалобы и пожелания).

Лёгкий канал обращений пользователей вне процесса заявок: житель оставляет
жалобу/пожелание (текст + необязательное фото) через бот или TWA, менеджеры
работают с обращениями в дашборде (статус new→in_review→resolved, ответ).
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from uk_management_bot.database.session import Base


class Feedback(Base):
    """Обращение обратной связи."""

    __tablename__ = "feedback"

    # PK уже индексирован — БЕЗ index=True (иначе лишний ix_feedback_id только на create_all-пути).
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # индекс owned миграцией 013

    type = Column(String(20), nullable=False)  # 'complaint' | 'wish'
    text = Column(Text, nullable=False)
    media_files = Column(JSON, default=list, nullable=True)  # list[int] — media-service media_id

    # server_default дублирует значение из миграции → схема после create_all и после Alembic совпадает.
    source = Column(String(20), default="bot", server_default="bot", nullable=False)  # 'bot' | 'twa'
    status = Column(
        String(20), default="new", server_default="new", nullable=False
    )  # 'new' | 'in_review' | 'resolved'

    # Ответ менеджера
    reply = Column(Text, nullable=True)
    replied_at = Column(DateTime(timezone=True), nullable=True)
    replied_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())  # индекс owned миграцией 013

    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return f"<Feedback(id={self.id}, type={self.type}, status={self.status})>"
