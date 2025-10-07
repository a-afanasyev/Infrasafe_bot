"""
Rate Limiting Middleware
UK Management Bot - Bot Gateway Service

Prevents flood and abuse using Redis-based rate limiting.
"""

import logging
from typing import Callable, Dict, Any, Awaitable
from datetime import datetime

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    """
    Rate Limiting Middleware

    Responsibilities:
    - Prevent flood attacks (too many messages per second)
    - Enforce rate limits per user (messages per minute/hour)
    - Track command usage limits
    - Store rate limit data in Redis
    """

    def __init__(self):
        """Initialize rate limiter with Redis connection"""
        self.redis: aioredis.Redis | None = None
        self.initialized = False

    async def _ensure_redis(self) -> None:
        """Ensure Redis connection is established"""
        if not self.initialized:
            try:
                self.redis = await aioredis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True
                )
                self.initialized = True
                logger.info("Rate limiter Redis connection established")
            except Exception as e:
                logger.error(f"Failed to connect to Redis for rate limiting: {e}")
                self.redis = None

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Check rate limits before processing update.

        Args:
            handler: Next handler in chain
            event: Telegram update
            data: Handler data dict

        Returns:
            Handler result or None if rate limited
        """
        if not settings.RATE_LIMIT_ENABLED:
            return await handler(event, data)

        await self._ensure_redis()

        if not self.redis:
            # Redis not available, proceed without rate limiting
            logger.warning("Rate limiting disabled: Redis not available")
            return await handler(event, data)

        # Extract user info
        telegram_id = None
        is_command = False

        if isinstance(event, Message):
            telegram_id = event.from_user.id if event.from_user else None
            is_command = event.text and event.text.startswith("/") if event.text else False
        elif isinstance(event, CallbackQuery):
            telegram_id = event.from_user.id if event.from_user else None

        if not telegram_id:
            # No user ID, skip rate limiting
            return await handler(event, data)

        # Check rate limits
        try:
            # Check messages per minute
            if not await self._check_limit(
                user_id=telegram_id,
                limit_type="messages_per_minute",
                max_count=settings.RATE_LIMIT_MESSAGES_PER_MINUTE,
                window_seconds=60
            ):
                logger.warning(
                    f"Rate limit exceeded: {telegram_id} - messages per minute"
                )
                if isinstance(event, Message):
                    await event.answer(
                        "⚠️ Слишком много сообщений. Пожалуйста, подождите немного.\n"
                        "⚠️ Juda ko'p xabarlar. Iltimos, biroz kuting."
                    )
                return None

            # Check messages per hour
            if not await self._check_limit(
                user_id=telegram_id,
                limit_type="messages_per_hour",
                max_count=settings.RATE_LIMIT_MESSAGES_PER_HOUR,
                window_seconds=3600
            ):
                logger.warning(
                    f"Rate limit exceeded: {telegram_id} - messages per hour"
                )
                if isinstance(event, Message):
                    await event.answer(
                        "⚠️ Превышен лимит сообщений в час. Попробуйте позже.\n"
                        "⚠️ Soatlik xabarlar limiti oshib ketdi. Keyinroq urinib ko'ring."
                    )
                return None

            # Check commands per minute (stricter limit)
            if is_command:
                if not await self._check_limit(
                    user_id=telegram_id,
                    limit_type="commands_per_minute",
                    max_count=settings.RATE_LIMIT_COMMANDS_PER_MINUTE,
                    window_seconds=60
                ):
                    logger.warning(
                        f"Rate limit exceeded: {telegram_id} - commands per minute"
                    )
                    if isinstance(event, Message):
                        await event.answer(
                            "⚠️ Слишком много команд. Пожалуйста, подождите.\n"
                            "⚠️ Juda ko'p buyruqlar. Iltimos, kuting."
                        )
                    return None

            # All checks passed, proceed to handler
            return await handler(event, data)

        except Exception as e:
            logger.error(f"Rate limiting error: {e}")
            # On error, allow request to proceed
            return await handler(event, data)

    async def _check_limit(
        self,
        user_id: int,
        limit_type: str,
        max_count: int,
        window_seconds: int
    ) -> bool:
        """
        Check if user is within rate limit.

        Uses sliding window algorithm with Redis.

        Args:
            user_id: Telegram user ID
            limit_type: Type of limit (messages_per_minute, etc.)
            max_count: Maximum allowed count
            window_seconds: Time window in seconds

        Returns:
            True if within limit, False if exceeded
        """
        if not self.redis:
            return True

        key = f"rate_limit:bot_gateway:{user_id}:{limit_type}"

        try:
            # Get current count
            current_count = await self.redis.get(key)

            if current_count is None:
                # First request in window, set counter
                await self.redis.setex(key, window_seconds, "1")
                return True

            current_count = int(current_count)

            if current_count >= max_count:
                # Limit exceeded
                return False

            # Increment counter
            await self.redis.incr(key)
            return True

        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            # On error, allow request
            return True

    async def close(self) -> None:
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
            logger.info("Rate limiter Redis connection closed")
