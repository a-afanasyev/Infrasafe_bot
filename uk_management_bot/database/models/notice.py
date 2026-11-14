"""Новости и уведомления жителям: единый источник витрины и рассылок.

Одна строка — одно сообщение УК жителям: ручная новость, плановое отключение,
одобренная новость из канала (news-watch) или отключение, объявленное
сотрудником. Табло, главная и TWA получают прежние ``announcements`` /
``planned_works``, но собранные из этой таблицы (services/notices/board.py),
а не из JSON ``board_config``.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from uk_management_bot.database.session import Base

NOTICE_KIND_NEWS = "news"
NOTICE_KIND_OUTAGE = "outage"
NOTICE_KINDS = (NOTICE_KIND_NEWS, NOTICE_KIND_OUTAGE)

NOTICE_SOURCE_MANUAL = "manual"
NOTICE_SOURCE_NEWS_WATCH = "news_watch"
NOTICE_SOURCE_STAFF = "staff"
NOTICE_SOURCES = (NOTICE_SOURCE_MANUAL, NOTICE_SOURCE_NEWS_WATCH, NOTICE_SOURCE_STAFF)

NOTICE_STATUS_DRAFT = "draft"
NOTICE_STATUS_PUBLISHED = "published"
NOTICE_STATUS_CLOSED = "closed"
NOTICE_STATUSES = (NOTICE_STATUS_DRAFT, NOTICE_STATUS_PUBLISHED, NOTICE_STATUS_CLOSED)

NOTICE_SCOPE_ALL = "all"
NOTICE_SCOPE_YARDS = "yards"
NOTICE_SCOPE_BUILDINGS = "buildings"
NOTICE_SCOPES = (NOTICE_SCOPE_ALL, NOTICE_SCOPE_YARDS, NOTICE_SCOPE_BUILDINGS)


class Notice(Base):
    __tablename__ = "notices"
    __table_args__ = (UniqueConstraint("news_item_id", name="uq_notices_news_item_id"),)

    id = Column(Integer, primary_key=True)
    kind = Column(String(20), nullable=False, default=NOTICE_KIND_NEWS)
    # Вид ресурса для отключения (значения NEWS_KINDS из news_item.py); у новости NULL.
    resource = Column(String(20), nullable=True)
    source = Column(String(20), nullable=False, default=NOTICE_SOURCE_MANUAL)
    news_item_id = Column(Integer, ForeignKey("news_items.id", ondelete="SET NULL"), nullable=True)

    title_ru = Column(Text, nullable=False, default="")
    title_uz = Column(Text, nullable=False, default="")
    text_ru = Column(Text, nullable=False, default="")
    text_uz = Column(Text, nullable=False, default="")
    place_ru = Column(Text, nullable=False, default="")
    place_uz = Column(Text, nullable=False, default="")
    icon = Column(String(16), nullable=False, default="")
    important = Column(Boolean, nullable=False, default=False)

    status = Column(String(20), nullable=False, default=NOTICE_STATUS_DRAFT, index=True)
    # Когда показать жителям (отложенная публикация); до этого момента запись
    # со статусом published на витрине не видна.
    publish_at = Column(DateTime(timezone=True), nullable=True, index=True)
    # Окно отключения. all_day — время начала/конца не названо («весь день»).
    starts_at = Column(DateTime(timezone=True), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)
    all_day = Column(Boolean, nullable=False, default=False)
    # Когда убрать с витрины (NULL — пока не закроют вручную).
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Адресаты рассылки (этап 2): все / дворы / дома; scope_ids — id справочника.
    scope = Column(String(20), nullable=False, default=NOTICE_SCOPE_ALL)
    scope_ids = Column(JSON, nullable=False, default=list)

    # Outbox рассылки — те же поля и смысл, что у news_items.broadcast_*.
    broadcast_status = Column(String(20), nullable=False, default="none", index=True)
    broadcast_attempts = Column(Integer, nullable=False, default=0)
    broadcast_next_at = Column(DateTime(timezone=True), nullable=True)
    broadcast_started_at = Column(DateTime(timezone=True), nullable=True)
    broadcast_cursor = Column(Integer, nullable=False, default=0)
    broadcast_details = Column(JSON, nullable=True)

    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<Notice(id={self.id}, kind={self.kind}, status={self.status})>"
