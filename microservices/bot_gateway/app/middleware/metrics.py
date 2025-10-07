"""
Bot Gateway Service - Metrics Middleware
UK Management Bot - Sprint 19-22

Middleware for automatic metrics collection from all bot interactions.
"""

import time
import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from app.core.metrics import (
    messages_total,
    message_processing_duration,
    commands_total,
    callbacks_total,
    callback_processing_duration,
    middleware_duration,
    exceptions_total,
)

logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseMiddleware):
    """
    Middleware to collect metrics from all bot interactions.

    Tracks:
    - Message counts by type, role, language
    - Processing duration for messages and callbacks
    - Command execution counts
    - Exceptions and errors
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Process event and collect metrics.

        Args:
            handler: Next handler in chain
            event: Telegram event (Message or CallbackQuery)
            data: Event data dictionary

        Returns:
            Handler result
        """
        start_time = time.time()

        # Get user context from previous middleware (AuthMiddleware)
        user_role = data.get("user_role", "unknown")
        language = data.get("language", "unknown")

        try:
            # Track message metrics
            if isinstance(event, Message):
                await self._track_message_metrics(event, user_role, language)

            # Track callback metrics
            elif isinstance(event, CallbackQuery):
                await self._track_callback_metrics(event, user_role, language)

            # Execute handler
            result = await handler(event, data)

            # Track processing duration
            duration = time.time() - start_time
            self._track_processing_duration(event, duration)

            return result

        except Exception as e:
            # Track exception
            handler_name = handler.__name__ if hasattr(handler, '__name__') else "unknown"
            exception_type = type(e).__name__

            exceptions_total.labels(
                exception_type=exception_type,
                handler=handler_name
            ).inc()

            logger.error(
                f"Exception in handler {handler_name}: {exception_type}",
                exc_info=True
            )

            # Re-raise exception for error handler
            raise

        finally:
            # Track middleware duration
            middleware_duration.labels(
                middleware_name="metrics"
            ).observe(time.time() - start_time)

    async def _track_message_metrics(
        self,
        message: Message,
        user_role: str,
        language: str
    ) -> None:
        """
        Track metrics for incoming messages.

        Args:
            message: Telegram Message object
            user_role: User role
            language: User language
        """
        # Determine message type
        message_type = self._get_message_type(message)

        # Increment message counter
        messages_total.labels(
            message_type=message_type,
            user_role=user_role,
            language=language
        ).inc()

        # Track commands separately
        if message.text and message.text.startswith('/'):
            command = message.text.split()[0].replace('/', '')
            commands_total.labels(
                command=command,
                user_role=user_role,
                status="received"
            ).inc()

    async def _track_callback_metrics(
        self,
        callback: CallbackQuery,
        user_role: str,
        language: str
    ) -> None:
        """
        Track metrics for callback queries.

        Args:
            callback: Telegram CallbackQuery object
            user_role: User role
            language: User language
        """
        # Extract callback type from callback_data
        callback_type = "unknown"
        if callback.data:
            callback_type = callback.data.split(':')[0] if ':' in callback.data else callback.data

        # Increment callback counter
        callbacks_total.labels(
            callback_type=callback_type,
            user_role=user_role,
            status="received"
        ).inc()

    def _track_processing_duration(
        self,
        event: TelegramObject,
        duration: float
    ) -> None:
        """
        Track processing duration for events.

        Args:
            event: Telegram event
            duration: Processing duration in seconds
        """
        if isinstance(event, Message):
            message_type = self._get_message_type(event)
            handler = "message_handler"

            message_processing_duration.labels(
                message_type=message_type,
                handler=handler
            ).observe(duration)

        elif isinstance(event, CallbackQuery):
            callback_type = "unknown"
            if event.data:
                callback_type = event.data.split(':')[0] if ':' in event.data else event.data

            callback_processing_duration.labels(
                callback_type=callback_type
            ).observe(duration)

    @staticmethod
    def _get_message_type(message: Message) -> str:
        """
        Determine message type from Message object.

        Args:
            message: Telegram Message object

        Returns:
            Message type as string
        """
        if message.text:
            if message.text.startswith('/'):
                return "command"
            return "text"
        elif message.photo:
            return "photo"
        elif message.document:
            return "document"
        elif message.voice:
            return "voice"
        elif message.video:
            return "video"
        elif message.audio:
            return "audio"
        elif message.sticker:
            return "sticker"
        elif message.location:
            return "location"
        elif message.contact:
            return "contact"
        else:
            return "other"
