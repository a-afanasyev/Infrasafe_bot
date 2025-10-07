"""
Bot Session Model
UK Management Bot - Bot Gateway Service

Stores user session data including FSM states and context.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from sqlalchemy import String, Text, BigInteger, DateTime, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import BaseModel


class BotSession(BaseModel):
    """
    Bot User Session

    Stores FSM state and context for each user's conversation.
    Replaces in-memory FSM storage with persistent database storage.
    """

    __tablename__ = "bot_sessions"

    # User identification
    user_id: Mapped[UUID] = mapped_column(
        nullable=False,
        index=True,
        comment="Reference to User Service user_id"
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        unique=True,
        index=True,
        comment="Telegram user ID"
    )

    # FSM State
    current_state: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Current FSM state (e.g., RequestCreation:waiting_for_description)"
    )

    state_data: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="FSM state context data"
    )

    # Session context
    context_json: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional session context (language, role, etc.)"
    )

    # Session management
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
        comment="Last user activity timestamp"
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
        comment="Session expiration timestamp"
    )

    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        comment="Session active status"
    )

    # User metadata
    username: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Telegram username"
    )

    first_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Telegram first name"
    )

    last_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Telegram last name"
    )

    language_code: Mapped[str] = mapped_column(
        String(10),
        default="ru",
        nullable=False,
        comment="User's language preference"
    )

    # Metadata
    platform_info: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Device/platform information"
    )

    # Indexes for performance
    __table_args__ = (
        Index("ix_bot_sessions_user_active", "user_id", "is_active"),
        Index("ix_bot_sessions_telegram_active", "telegram_id", "is_active"),
        Index("ix_bot_sessions_expires", "expires_at", "is_active"),
    )

    def __repr__(self) -> str:
        return (
            f"<BotSession(telegram_id={self.telegram_id}, "
            f"state={self.current_state}, "
            f"active={self.is_active})>"
        )
