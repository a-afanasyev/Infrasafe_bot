"""
Logging Middleware
UK Management Bot - Bot Gateway Service

Logs all incoming messages and callbacks with metrics tracking.
"""

import logging
import time
from typing import Callable, Dict, Any, Awaitable
from datetime import datetime

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from app.core.database import AsyncSessionLocal
from app.models.bot_metric import BotMetric

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """
    Logging Middleware

    Responsibilities:
    - Log all incoming messages and callbacks
    - Track message processing time
    - Store metrics in database
    - Provide request context for debugging
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Log incoming update and track processing time.

        Args:
            handler: Next handler in chain
            event: Telegram update
            data: Handler data dict

        Returns:
            Handler result
        """
        start_time = time.time()
        event_type = type(event).__name__
        user_id = None
        telegram_id = None
        chat_id = None
        message_text = None
        callback_data = None

        # Extract event details
        try:
            if isinstance(event, Message):
                user_id = data.get("user_id")
                telegram_id = event.from_user.id if event.from_user else None
                chat_id = event.chat.id if event.chat else None
                message_text = event.text or event.caption or f"[{event.content_type}]"

                logger.info(
                    f"📨 Message from {telegram_id} (chat {chat_id}): {message_text[:50]}"
                )

            elif isinstance(event, CallbackQuery):
                user_id = data.get("user_id")
                telegram_id = event.from_user.id if event.from_user else None
                chat_id = event.message.chat.id if event.message and event.message.chat else None
                callback_data = event.data

                logger.info(
                    f"🔘 Callback from {telegram_id}: {callback_data}"
                )

        except Exception as e:
            logger.error(f"Error extracting event details: {e}")

        # Call next handler
        try:
            result = await handler(event, data)

            # Calculate processing time
            duration_ms = (time.time() - start_time) * 1000

            # Log success
            logger.info(
                f"✅ {event_type} processed in {duration_ms:.2f}ms "
                f"(telegram_id={telegram_id})"
            )

            # Store metric asynchronously (don't block on this)
            try:
                await self._store_metric(
                    event_type=event_type,
                    user_id=user_id,
                    telegram_id=telegram_id,
                    duration_ms=duration_ms,
                    status="success",
                    message_text=message_text,
                    callback_data=callback_data
                )
            except Exception as e:
                logger.error(f"Failed to store metric: {e}")

            return result

        except Exception as e:
            # Calculate processing time
            duration_ms = (time.time() - start_time) * 1000

            # Log error
            logger.error(
                f"❌ {event_type} failed after {duration_ms:.2f}ms "
                f"(telegram_id={telegram_id}): {e}",
                exc_info=True
            )

            # Store error metric
            try:
                await self._store_metric(
                    event_type=event_type,
                    user_id=user_id,
                    telegram_id=telegram_id,
                    duration_ms=duration_ms,
                    status="error",
                    error_message=str(e),
                    message_text=message_text,
                    callback_data=callback_data
                )
            except Exception as metric_error:
                logger.error(f"Failed to store error metric: {metric_error}")

            # Re-raise exception
            raise

    async def _store_metric(
        self,
        event_type: str,
        user_id: str | None,
        telegram_id: int | None,
        duration_ms: float,
        status: str,
        message_text: str | None = None,
        callback_data: str | None = None,
        error_message: str | None = None
    ) -> None:
        """
        Store processing metric in database.

        Args:
            event_type: Type of event (Message, CallbackQuery)
            user_id: User UUID
            telegram_id: Telegram user ID
            duration_ms: Processing duration in milliseconds
            status: success or error
            message_text: Message text (if Message)
            callback_data: Callback data (if CallbackQuery)
            error_message: Error message (if error)
        """
        async with AsyncSessionLocal() as db:
            try:
                now = datetime.utcnow()

                # Create response time metric
                response_metric = BotMetric(
                    metric_type="response_time",
                    metric_name=f"{event_type.lower()}_response",
                    value=duration_ms,
                    unit="ms",
                    user_id=user_id,
                    telegram_id=telegram_id,
                    timestamp=now,
                    date=now.date(),
                    hour=now.hour,
                    status=status,
                    handler_service="bot_gateway",
                    metadata={
                        "event_type": event_type,
                        "message_text": message_text[:100] if message_text else None,
                        "callback_data": callback_data
                    }
                )
                db.add(response_metric)

                # Create user action metric
                action_metric = BotMetric(
                    metric_type="user_action",
                    metric_name=event_type.lower(),
                    value=1.0,
                    unit="count",
                    user_id=user_id,
                    telegram_id=telegram_id,
                    timestamp=now,
                    date=now.date(),
                    hour=now.hour,
                    status=status,
                    handler_service="bot_gateway",
                    metadata={
                        "event_type": event_type,
                        "duration_ms": duration_ms
                    }
                )
                db.add(action_metric)

                # Create error metric if error occurred
                if status == "error" and error_message:
                    error_metric = BotMetric(
                        metric_type="error",
                        metric_name=f"{event_type.lower()}_error",
                        value=1.0,
                        unit="count",
                        user_id=user_id,
                        telegram_id=telegram_id,
                        timestamp=now,
                        date=now.date(),
                        hour=now.hour,
                        status="error",
                        error_message=error_message[:500],
                        handler_service="bot_gateway",
                        metadata={
                            "event_type": event_type,
                            "message_text": message_text[:100] if message_text else None,
                            "callback_data": callback_data
                        }
                    )
                    db.add(error_metric)

                await db.commit()

            except Exception as e:
                logger.error(f"Failed to store metrics: {e}")
                await db.rollback()
