"""Simple per-user message throttling middleware."""
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

_EVICTION_THRESHOLD = 10_000


class ThrottlingMiddleware(BaseMiddleware):
    """Drop messages from users who exceed rate_limit (seconds between messages)."""

    def __init__(self, rate_limit: float = 0.5):
        self.rate_limit = rate_limit
        self._last_message: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        user_id = event.from_user.id if event.from_user else 0
        now = time.monotonic()
        last = self._last_message.get(user_id, 0.0)

        if now - last < self.rate_limit:
            return None

        self._last_message[user_id] = now

        # Evict stale entries to prevent unbounded memory growth
        if len(self._last_message) > _EVICTION_THRESHOLD:
            cutoff = now - self.rate_limit
            self._last_message = {
                k: v for k, v in self._last_message.items() if v >= cutoff
            }

        return await handler(event, data)
