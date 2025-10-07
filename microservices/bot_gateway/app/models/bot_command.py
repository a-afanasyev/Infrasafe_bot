"""
Bot Command Model
UK Management Bot - Bot Gateway Service

Stores bot command configurations and routing information.
"""

from typing import Optional, List
from sqlalchemy import String, Text, Boolean, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .base import BaseModel


class BotCommand(BaseModel):
    """
    Bot Command Configuration

    Maps bot commands to handler services and defines access control.
    Examples: /start, /help, /create_request, /my_shifts
    """

    __tablename__ = "bot_commands"

    # Command details
    command: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Command name (e.g., 'start', 'help', 'create_request')"
    )

    description: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Command description (shown in bot menu)"
    )

    description_ru: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="Russian description"
    )

    description_uz: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="Uzbek description"
    )

    # Routing
    handler_service: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Target microservice: bot_gateway, request_service, shift_service, etc."
    )

    handler_path: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="API endpoint path in target service"
    )

    # Access control
    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        index=True,
        comment="Command enabled status"
    )

    required_roles: Mapped[Optional[List[str]]] = mapped_column(
        JSON,
        nullable=True,
        comment="Required user roles: ['admin', 'manager', 'executor', 'applicant']"
    )

    requires_auth: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        comment="Whether command requires authentication"
    )

    # Command metadata
    category: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="Command category: general, requests, shifts, admin"
    )

    icon: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="Emoji icon for command"
    )

    sort_order: Mapped[int] = mapped_column(
        default=100,
        nullable=False,
        comment="Display order in bot menu"
    )

    # Usage tracking
    usage_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
        comment="Total times command has been used"
    )

    # Configuration
    config: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional command configuration"
    )

    # Indexes for performance
    __table_args__ = (
        Index("ix_bot_commands_active_category", "is_active", "category"),
        Index("ix_bot_commands_handler", "handler_service", "is_active"),
    )

    def __repr__(self) -> str:
        return (
            f"<BotCommand(command=/{self.command}, "
            f"service={self.handler_service}, "
            f"active={self.is_active})>"
        )

    def is_available_for_role(self, user_role: str) -> bool:
        """
        Check if command is available for given user role.

        Args:
            user_role: User's role (admin, manager, executor, applicant)

        Returns:
            True if command is available, False otherwise
        """
        if not self.is_active:
            return False

        if not self.required_roles:
            return True

        return user_role in self.required_roles
