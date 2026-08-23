"""Реестр ТГ-групп, которые мониторит бот (Group Intake).

kind:
- ``residents`` — жительская группа: бот распознаёт заявки и предлагает
  автору создать заявку кнопкой (v1).
- ``staff`` — сотрудническая группа (фаза 2): репортёры — сотрудники,
  приёмка менеджерская (``acceptance_mode='manager'``).

require_tag (решение владельца 2026-08-23): группа в тег-режиме — бот
обрабатывает ТОЛЬКО сообщения с тегом ``#заявка``/``#ariza``; остальное
не уходит в LLM вовсе (приватность/стоимость/ноль ложных срабатываний).
Дефолт False — жительские группы продолжают авто-отлов.
"""
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.sql import func

from uk_management_bot.database.session import Base

GROUP_KIND_RESIDENTS = "residents"
GROUP_KIND_STAFF = "staff"
GROUP_KINDS = (GROUP_KIND_RESIDENTS, GROUP_KIND_STAFF)

# Теги-триггеры для групп в require_tag-режиме (сравнение casefold).
REQUEST_TAGS = ("#заявка", "#ariza")


class MonitoredGroup(Base):
    __tablename__ = "monitored_groups"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('residents', 'staff')", name="ck_monitored_groups_kind"
        ),
    )

    id = Column(Integer, primary_key=True)

    # Telegram chat id; у supergroup вид -100xxxxxxxxxx — только BigInteger.
    chat_id = Column(BigInteger, unique=True, nullable=False, index=True)

    title = Column(String(255), nullable=True)
    kind = Column(String(20), nullable=False, default=GROUP_KIND_RESIDENTS)
    is_active = Column(Boolean, nullable=False, default=True)
    require_tag = Column(
        Boolean, nullable=False, server_default="false", default=False
    )

    created_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return (
            f"<MonitoredGroup(id={self.id}, chat_id={self.chat_id}, "
            f"kind={self.kind}, is_active={self.is_active})>"
        )
