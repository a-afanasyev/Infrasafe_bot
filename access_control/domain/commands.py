"""Transactional outbox команд шлагбаума. §9.2, §10.1.

``barrier_commands`` — отдельный outbox (НЕ webhook_outbox): claim/lease под
``GET /commands/next``, ACK compare-and-set по ``(command_id, lease_token)``,
retry/dead-letter worker. PK — ``command_id`` (UUID, §9.2). ``UNIQUE(decision_id)
WHERE decision_id IS NOT NULL`` (§10.1): идемпотентная команда на одно решение;
ручные открытия (decision_id NULL) связываются через manual_openings.command_id.
"""
from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)

from uk_management_bot.database.session import Base
from .base import JSONB_PORTABLE, Uuid, created_at_column, updated_at_column
from .enums import CommandStatus, CommandType, in_clause


class BarrierCommand(Base):
    """Команда открытия шлагбаума в durable outbox (§9.2)."""

    __tablename__ = "barrier_commands"

    # PK — UUID command_id (§9.2): edge дедуплицирует по нему, исполняет реле ≤1 раза.
    command_id = Column(Uuid(), primary_key=True)
    # Источник команды: автоматическое решение (NULL для ручных открытий).
    decision_id = Column(
        ForeignKey("access_decisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    controller_id = Column(
        ForeignKey("edge_controllers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    barrier_id = Column(
        ForeignKey("access_barriers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    command_type = Column(
        String(32), nullable=False, server_default=CommandType.OPEN_BARRIER.value
    )
    status = Column(
        String(16), nullable=False, server_default=CommandStatus.PENDING.value
    )
    # Lease для атомарного claim под /commands/next (§9.2). Хранится SHA256-ХЭШ
    # выданного токена (at-rest), а не сырой токен (миграция 031, как у B):
    # перехват значения из БД не позволяет заакать. varchar(64) = длина sha256-hex.
    lease_token = Column(String(64), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    leased_at = Column(DateTime(timezone=True), nullable=True)
    attempts = Column(Integer, nullable=False, server_default="0")
    max_attempts = Column(Integer, nullable=False, server_default="5")
    expires_at = Column(DateTime(timezone=True), nullable=True)
    acked_at = Column(DateTime(timezone=True), nullable=True)
    # Сохранённый результат исполнения реле (§9.2): повторный ACK после потери
    # ответа возвращает его БЕЗ повторного исполнения. JSONB.
    ack_result = Column(JSONB_PORTABLE, nullable=True)
    # retry/dead-letter (§9.2): момент перевода в dead и последняя ошибка.
    dead_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = created_at_column()
    updated_at = updated_at_column()

    __table_args__ = (
        CheckConstraint(
            in_clause("status", CommandStatus), name="ck_barrier_commands_status"
        ),
        CheckConstraint(
            in_clause("command_type", CommandType),
            name="ck_barrier_commands_command_type",
        ),
        # Идемпотентность §10.1: одна команда на решение (ручные — decision_id NULL).
        Index(
            "uq_barrier_commands_decision",
            "decision_id",
            unique=True,
            postgresql_where=text("decision_id IS NOT NULL"),
            sqlite_where=text("decision_id IS NOT NULL"),
        ),
        # Очередь pending по контроллеру (claim/lease ORDER BY created_at).
        Index("ix_barrier_commands_controller_status", "controller_id", "status"),
    )
