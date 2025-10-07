"""
Authentication Middleware
UK Management Bot - Bot Gateway Service

Handles user authentication via Auth Service.
"""

import logging
from typing import Callable, Dict, Any, Awaitable
from datetime import datetime, timedelta

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.bot_session import BotSession
from app.integrations.auth_client import auth_client

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    """
    Authentication Middleware

    Responsibilities:
    - Authenticate user via Auth Service on first interaction
    - Load or create bot session
    - Store JWT token in session for subsequent requests
    - Refresh expired tokens
    - Provide user context to handlers via data["user"] and data["token"]
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Process authentication for incoming update.

        Args:
            handler: Next handler in chain
            event: Telegram update (Message, CallbackQuery, etc.)
            data: Handler data dict

        Returns:
            Handler result
        """
        # Extract user from event
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if not user:
            # No user in event, skip authentication
            return await handler(event, data)

        # Get or create database session
        async with AsyncSessionLocal() as db:
            try:
                # Load or create bot session
                bot_session = await self._get_or_create_session(
                    db=db,
                    telegram_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    language_code=user.language_code or "ru"
                )

                # Check if session has valid token
                token = await self._get_valid_token(bot_session)

                if not token:
                    # Authenticate user via Auth Service
                    try:
                        auth_result = await auth_client.login_telegram(
                            telegram_id=user.id,
                            username=user.username,
                            first_name=user.first_name,
                            last_name=user.last_name
                        )
                        token = auth_result.get("access_token")

                        # Store token in session context
                        if not bot_session.context_json:
                            bot_session.context_json = {}
                        bot_session.context_json["access_token"] = token
                        bot_session.context_json["token_expires_at"] = (
                            datetime.utcnow() + timedelta(
                                minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
                            )
                        ).isoformat()

                        # Store user info
                        user_info = auth_result.get("user", {})
                        bot_session.context_json["user_id"] = str(user_info.get("id"))
                        bot_session.context_json["role"] = user_info.get("role")

                        await db.commit()

                        logger.info(
                            f"User authenticated: telegram_id={user.id}, "
                            f"user_id={user_info.get('id')}, role={user_info.get('role')}"
                        )

                    except Exception as e:
                        logger.error(f"Authentication failed for telegram_id={user.id}: {e}")
                        # Allow handler to proceed without token (will fail if requires auth)
                        token = None

                # Update last activity
                bot_session.last_activity_at = datetime.utcnow()
                await db.commit()

                # Provide user context to handler
                data["bot_session"] = bot_session
                data["token"] = token
                data["user_id"] = bot_session.context_json.get("user_id") if bot_session.context_json else None
                data["user_role"] = bot_session.context_json.get("role") if bot_session.context_json else None
                data["language"] = bot_session.language_code

                # Call next handler
                return await handler(event, data)

            except Exception as e:
                logger.error(f"Auth middleware error: {e}", exc_info=True)
                # Continue without authentication
                return await handler(event, data)

    async def _get_or_create_session(
        self,
        db: AsyncSession,
        telegram_id: int,
        username: str = None,
        first_name: str = None,
        last_name: str = None,
        language_code: str = "ru"
    ) -> BotSession:
        """
        Get existing session or create new one.

        Args:
            db: Database session
            telegram_id: Telegram user ID
            username: Telegram username
            first_name: Telegram first name
            last_name: Telegram last name
            language_code: Language code

        Returns:
            Bot session
        """
        from sqlalchemy import select

        # Try to find existing session
        result = await db.execute(
            select(BotSession).where(
                BotSession.telegram_id == telegram_id,
                BotSession.is_active == True
            )
        )
        session = result.scalar_one_or_none()

        if session:
            # Update user info if changed
            if username and session.username != username:
                session.username = username
            if first_name and session.first_name != first_name:
                session.first_name = first_name
            if last_name and session.last_name != last_name:
                session.last_name = last_name

            # Check if session expired
            if datetime.utcnow() >= session.expires_at:
                # Extend session
                session.expires_at = datetime.utcnow() + timedelta(
                    seconds=settings.session_lifetime_seconds
                )
                logger.info(f"Session extended for telegram_id={telegram_id}")

            return session

        # Create new session
        session = BotSession(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            user_id=None,  # Will be set after authentication
            expires_at=datetime.utcnow() + timedelta(
                seconds=settings.session_lifetime_seconds
            ),
            is_active=True
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)

        logger.info(f"New session created for telegram_id={telegram_id}")
        return session

    async def _get_valid_token(self, bot_session: BotSession) -> str | None:
        """
        Get valid JWT token from session.

        Returns None if token is missing or expired.

        Args:
            bot_session: Bot session

        Returns:
            Valid JWT token or None
        """
        if not bot_session.context_json:
            return None

        token = bot_session.context_json.get("access_token")
        if not token:
            return None

        # Check token expiration
        expires_at_str = bot_session.context_json.get("token_expires_at")
        if not expires_at_str:
            return None

        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.utcnow() >= expires_at:
                logger.info(f"Token expired for telegram_id={bot_session.telegram_id}")
                return None
        except Exception as e:
            logger.error(f"Error parsing token expiration: {e}")
            return None

        return token
