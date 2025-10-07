"""
Inline Keyboard Cache Model
UK Management Bot - Bot Gateway Service

Caches inline keyboard data for callback query handling.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from sqlalchemy import String, BigInteger, DateTime, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import BaseModel


class InlineKeyboardCache(BaseModel):
    """
    Inline Keyboard Cache

    Stores inline keyboard data to handle callback queries efficiently.
    Prevents need to reconstruct keyboard state from scratch.
    """

    __tablename__ = "inline_keyboard_cache"

    # Message identification
    message_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Telegram message ID with inline keyboard"
    )

    chat_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Telegram chat ID"
    )

    user_id: Mapped[UUID] = mapped_column(
        nullable=False,
        index=True,
        comment="Reference to User Service user_id"
    )

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        comment="Telegram user ID"
    )

    # Keyboard data
    keyboard_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Keyboard type: request_actions, shift_selection, admin_menu, etc."
    )

    keyboard_data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Full inline keyboard configuration"
    )

    # Context for callback handling
    callback_context: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Context data for callback query processing"
    )

    # Related entities
    related_entity_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="Related entity type: request, shift, user, etc."
    )

    related_entity_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Related entity ID (request_number, shift_id, etc.)"
    )

    # Cache management
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True,
        comment="Cache expiration timestamp"
    )

    is_valid: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        index=True,
        comment="Cache validity status"
    )

    # Usage tracking
    callback_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
        comment="Number of times callback has been processed"
    )

    last_callback_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="Last callback processing timestamp"
    )

    # Metadata
    metadata: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional metadata"
    )

    # Indexes for performance
    __table_args__ = (
        Index("ix_keyboard_cache_message", "chat_id", "message_id"),
        Index("ix_keyboard_cache_user_type", "user_id", "keyboard_type"),
        Index("ix_keyboard_cache_entity", "related_entity_type", "related_entity_id"),
        Index("ix_keyboard_cache_expires", "expires_at", "is_valid"),
    )

    def __repr__(self) -> str:
        return (
            f"<InlineKeyboardCache(message_id={self.message_id}, "
            f"type={self.keyboard_type}, "
            f"valid={self.is_valid})>"
        )

    def is_expired(self) -> bool:
        """Check if cache entry has expired"""
        return datetime.utcnow() >= self.expires_at

    def invalidate(self) -> None:
        """Invalidate cache entry"""
        self.is_valid = False
