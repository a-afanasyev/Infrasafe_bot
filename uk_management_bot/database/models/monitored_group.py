"""Реестр ТГ-групп, которые мониторит бот (Group Intake).

kind:
- ``residents`` — жительская группа: бот распознаёт заявки и предлагает
  автору создать заявку кнопкой (v1).
- ``staff`` — сотрудническая группа: обработка появится в фазе 2 (после
  решения владельца о модели приёмки); в v1 бот такие группы игнорирует,
  но тип заводится сразу, чтобы не мигрировать схему повторно.
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
