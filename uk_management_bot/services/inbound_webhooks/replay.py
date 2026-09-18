"""Replay/duplicate detection for inbound webhooks via a Redis nonce cache.

Each accepted webhook's event_id is recorded with a TTL. A repeated event_id
within the window is a replay. TTL is 2× the signature timestamp window — past
that, the signature staleness check rejects anyway.

Redis unavailable → fail-open (D3): HMAC has already proven authenticity, so a
duplicate getting through is safer than dropping a legitimate event.
"""
import logging

import redis.asyncio as aioredis

from uk_management_bot.config.settings import settings

logger = logging.getLogger(__name__)

_REPLAY_TTL_SEC = 600
_KEY_PREFIX = "webhook:inbound:nonce:"

_client: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


async def is_replay(event_id: str) -> bool:
    """True if `event_id` was already seen within the TTL window.

    Records the event_id atomically via SET NX EX. Fail-open: on any Redis
    error logs a warning and returns False (treat as not-a-replay).
    """
    try:
        client = await _get_redis()
        was_set = await client.set(
            f"{_KEY_PREFIX}{event_id}", "1", nx=True, ex=_REPLAY_TTL_SEC
        )
        return not was_set
    except Exception:
        logger.warning(
            "replay check: Redis unavailable, fail-open (event_id=%s)",
            event_id, exc_info=True,
        )
        return False
