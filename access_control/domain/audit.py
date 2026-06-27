"""Ручные открытия и аудит. §9.5, §9.7.

``manual_openings`` — ручное открытие оператором с обязательной причиной (§9.5);
создаёт команду в barrier_commands (ссылка command_id). Append-only (§9.7).
``access_audit_logs`` — журнал административных/операторских действий. Append-only
(§9.7). Обе несут hash-chain (prev_hash/row_hash, решение CTO #9).
"""
from __future__ import annotations

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
)

from uk_management_bot.database.session import Base
from .base import (
    HashChainMixin,
    JSONB_PORTABLE,
    Uuid,
    created_at_column,
    pk_column,
)


class ManualOpening(Base, HashChainMixin):
    """Ручное открытие шлагбаума оператором (§9.5). Append-only (§9.7)."""

    __tablename__ = "manual_openings"

    id = pk_column()
    barrier_id = Column(
        ForeignKey("access_barriers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Команда, созданная этим открытием (§9.5 → barrier_commands).
    command_id = Column(
        Uuid(),
        ForeignKey("barrier_commands.command_id", ondelete="SET NULL"),
        nullable=True,
    )
    # Решение manual_review, которое резолвит это открытие (§9.5), если применимо.
    decision_id = Column(
        ForeignKey("access_decisions.id", ondelete="SET NULL"), nullable=True
    )
    operator_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reason = Column(Text, nullable=False)
    captured_event_id = Column(
        ForeignKey("camera_events.id", ondelete="SET NULL"), nullable=True
    )
    created_at = created_at_column()


class AccessAuditLog(Base, HashChainMixin):
    """Журнал административных/операторских действий. Append-only (§9.7)."""

    __tablename__ = "access_audit_logs"

    id = pk_column()
    actor_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action = Column(String(128), nullable=False)
    entity_type = Column(String(64), nullable=True)
    entity_id = Column(String(64), nullable=True)
    details = Column(JSONB_PORTABLE, nullable=True)
    ip_address = Column(String(64), nullable=True)
    created_at = created_at_column()
