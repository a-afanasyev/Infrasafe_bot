"""Мониторинг отключений: новость из внешнего Telegram-источника.

Юзербот (news_watcher) кладёт сырой текст в inbox API; конвейер
(services/news_watch/pipeline) решает LLM-ом, касается ли новость нашего
комплекса, и переводит строку в pending (ждёт одобрения менеджера) или
published (auto_publish). Рассылка жителям — outbox-полями broadcast_*:
воркер API-процесса продолжает с курсора после падения, без дублей.
"""
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from uk_management_bot.database.session import Base

NEWS_STATUS_PENDING = "pending"
NEWS_STATUS_IGNORED = "ignored"
NEWS_STATUS_PUBLISHED = "published"
NEWS_STATUS_REJECTED = "rejected"
NEWS_STATUSES = (NEWS_STATUS_PENDING, NEWS_STATUS_IGNORED, NEWS_STATUS_PUBLISHED, NEWS_STATUS_REJECTED)

BROADCAST_NONE = "none"
BROADCAST_PENDING = "pending"
BROADCAST_RUNNING = "running"
BROADCAST_DONE = "done"
BROADCAST_FAILED = "failed"

NEWS_KINDS = ("power", "water", "gas", "heating", "internet", "other")


class NewsItem(Base):
    __tablename__ = "news_items"
    __table_args__ = (
        UniqueConstraint("source_chat_id", "source_message_id", name="uq_news_items_source"),
    )

    id = Column(Integer, primary_key=True)
    source_chat_id = Column(BigInteger, nullable=False)
    source_message_id = Column(BigInteger, nullable=False)
    chat_title = Column(String(255), nullable=True)
    raw_text = Column(Text, nullable=False)
    posted_at = Column(DateTime(timezone=True), nullable=True)

    # Решение LLM (None — не вызывался: отсеян префильтром по ключевым словам).
    kind = Column(String(20), nullable=True)
    relevant = Column(Boolean, nullable=True)
    confidence = Column(Float, nullable=True)
    summary_ru = Column(Text, nullable=True)
    summary_uz = Column(Text, nullable=True)
    starts_at = Column(DateTime(timezone=True), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)

    status = Column(String(20), nullable=False, default=NEWS_STATUS_PENDING, index=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    decided_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Outbox рассылки: воркер берёт pending/failed с next_at <= now и attempts < 5.
    broadcast_status = Column(String(20), nullable=False, default=BROADCAST_NONE, index=True)
    broadcast_attempts = Column(Integer, nullable=False, default=0)
    broadcast_next_at = Column(DateTime(timezone=True), nullable=True)
    broadcast_started_at = Column(DateTime(timezone=True), nullable=True)
    broadcast_cursor = Column(Integer, nullable=False, default=0)  # последний users.id
    broadcast_details = Column(JSON, nullable=True)  # отправленные группы, счётчики

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<NewsItem(id={self.id}, status={self.status}, kind={self.kind})>"


class NewsWatchConfig(Base):
    """Singleton-конфиг мониторинга (id=1): источники, описание комплекса,
    ключевые слова, auto_publish. Клон auto_manager_config."""

    __tablename__ = "news_watch_config"

    id = Column(Integer, primary_key=True)
    data = Column(JSON, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    def __repr__(self):
        return f"<NewsWatchConfig(id={self.id}, updated_at={self.updated_at})>"
