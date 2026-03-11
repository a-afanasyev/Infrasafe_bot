import json
import logging
import redis.asyncio as aioredis
from uk_management_bot.config.settings import settings

logger = logging.getLogger(__name__)

CHANNEL = "requests:updates"
_redis_client = None


async def get_pubsub_redis():
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.ping()
        except Exception:
            logger.warning("Redis pubsub connection lost, reconnecting")
            _redis_client = None
    if _redis_client is None:
        url = getattr(settings, 'REDIS_PUBSUB_URL', 'redis://redis:6379/1')
        _redis_client = aioredis.from_url(url, decode_responses=True)
    return _redis_client


async def publish_request_event(event_type: str, data: dict) -> None:
    """Publish event to Redis Pub/Sub channel. Called from API after request changes."""
    try:
        client = await get_pubsub_redis()
        message = json.dumps({"type": event_type, "data": data})
        await client.publish(CHANNEL, message)
    except Exception:
        logger.warning("Failed to publish event %s", event_type, exc_info=True)


async def subscribe_to_requests():
    """Returns a dedicated Redis Pub/Sub subscriber. Each caller gets its own connection."""
    url = getattr(settings, 'REDIS_PUBSUB_URL', 'redis://redis:6379/1')
    client = aioredis.from_url(url, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(CHANNEL)
    return pubsub


SHIFTS_CHANNEL = "shifts:updates"


async def publish_shift_event(event_type: str, data: dict) -> None:
    """Publish shift event to Redis Pub/Sub channel."""
    try:
        client = await get_pubsub_redis()
        message = json.dumps({"type": event_type, "data": data})
        await client.publish(SHIFTS_CHANNEL, message)
    except Exception:
        logger.warning("Failed to publish shift event %s", event_type, exc_info=True)


async def subscribe_to_shifts():
    """Returns a dedicated Redis Pub/Sub subscriber. Each caller gets its own connection."""
    url = getattr(settings, 'REDIS_PUBSUB_URL', 'redis://redis:6379/1')
    client = aioredis.from_url(url, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(SHIFTS_CHANNEL)
    return pubsub
