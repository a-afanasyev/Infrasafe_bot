import asyncio
import json
import logging
import redis.asyncio as aioredis
from uk_management_bot.config.settings import settings

logger = logging.getLogger(__name__)

# AUD3-08: у publisher'а и подписчика РАЗНЫЕ профили таймаутов, и это не
# стилистика. Раньше таймаутов не было ни у кого: зависший Redis (принимает
# TCP, но не отвечает — в отличие от «лёг», который даёт мгновенный отказ)
# блокировал вызывающего навсегда, а publisher дёргается прямо из обработчика
# HTTP-запроса.
#
# Publisher: короткий round-trip, ждать вечно нельзя → ограничены и соединение,
# и операция.
_PUBLISH_CONNECT_TIMEOUT = 2.0
_PUBLISH_OP_TIMEOUT = 2.0

# Подписчик: операционного таймаута быть НЕ ДОЛЖНО. `listen()`/`get_message()`
# на тихом канале ждут по замыслу — часами, если событий нет. Выставить им
# `socket_timeout` значит рвать живое соединение на первой же паузе; вместо
# этого мёртвое соединение обнаруживает health-check (клиент сам шлёт PING в
# простое), а зависание на самом handshake ограничивает `wait_for` ниже.
_SUBSCRIBE_CONNECT_TIMEOUT = 2.0
_SUBSCRIBE_HEALTH_CHECK_INTERVAL = 30.0
_SUBSCRIBE_HANDSHAKE_TIMEOUT = 5.0

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
        url = settings.REDIS_PUBSUB_URL_RESOLVED
        _redis_client = aioredis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=_PUBLISH_CONNECT_TIMEOUT,
            socket_timeout=_PUBLISH_OP_TIMEOUT,
        )
    return _redis_client


async def _subscriber(channel: str):
    """Выделенное соединение-подписчик на канал.

    Пять фабрик ниже были посимвольными копиями этого тела; профиль таймаутов
    обязан быть у всех один, а пять копий именно так и разъезжаются.

    Неудачный `subscribe()` закрывает клиента: раньше исключение здесь теряло
    соединение — вернуть его было уже некому, и оно оставалось открытым.
    """
    client = aioredis.from_url(
        settings.REDIS_PUBSUB_URL_RESOLVED,
        decode_responses=True,
        socket_connect_timeout=_SUBSCRIBE_CONNECT_TIMEOUT,
        health_check_interval=_SUBSCRIBE_HEALTH_CHECK_INTERVAL,
    )
    pubsub = client.pubsub()
    try:
        await asyncio.wait_for(
            pubsub.subscribe(channel), timeout=_SUBSCRIBE_HANDSHAKE_TIMEOUT
        )
    except BaseException:
        try:
            await client.aclose()
        except Exception:
            logger.warning("Не удалось закрыть redis-клиент после неудачной подписки на %s",
                           channel, exc_info=True)
        raise
    return pubsub, client


async def publish_request_event(event_type: str, data: dict) -> None:
    """Publish event to Redis Pub/Sub channel. Called from API after request changes."""
    try:
        client = await get_pubsub_redis()
        message = json.dumps({"type": event_type, "data": data})
        await client.publish(CHANNEL, message)
    except Exception:
        logger.warning("Failed to publish event %s", event_type, exc_info=True)


async def subscribe_to_requests():
    """Выделенное соединение-подписчик (профиль — в `_subscriber`)."""
    return await _subscriber(CHANNEL)


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
    """Выделенное соединение-подписчик (профиль — в `_subscriber`)."""
    return await _subscriber(SHIFTS_CHANNEL)


BUILDINGS_CHANNEL = "buildings:updates"


async def publish_building_event(event_type: str, data: dict) -> None:
    """Publish building event to Redis Pub/Sub for real-time frontend updates.

    NOTE: This is for frontend WebSocket push only, NOT for webhook delivery
    (webhooks use PostgreSQL outbox — see webhook_sender.py).
    """
    try:
        client = await get_pubsub_redis()
        message = json.dumps({"type": event_type, "data": data})
        await client.publish(BUILDINGS_CHANNEL, message)
    except Exception:
        logger.warning("Failed to publish building event %s", event_type, exc_info=True)


async def subscribe_to_buildings():
    """Выделенное соединение-подписчик (профиль — в `_subscriber`)."""
    return await _subscriber(BUILDINGS_CHANNEL)


YARDS_CHANNEL = "yards:updates"


async def publish_yard_event(event_type: str, data: dict) -> None:
    """Publish yard event to Redis Pub/Sub for real-time frontend updates.

    NOTE: frontend WebSocket push only, NOT webhook delivery.
    """
    try:
        client = await get_pubsub_redis()
        message = json.dumps({"type": event_type, "data": data})
        await client.publish(YARDS_CHANNEL, message)
    except Exception:
        logger.warning("Failed to publish yard event %s", event_type, exc_info=True)


async def subscribe_to_yards():
    """Выделенное соединение-подписчик (профиль — в `_subscriber`)."""
    return await _subscriber(YARDS_CHANNEL)


APARTMENTS_CHANNEL = "apartments:updates"


async def publish_apartment_event(event_type: str, data: dict) -> None:
    """Publish apartment event to Redis Pub/Sub for real-time frontend updates.

    NOTE: frontend WebSocket push only, NOT webhook delivery.
    """
    try:
        client = await get_pubsub_redis()
        message = json.dumps({"type": event_type, "data": data})
        await client.publish(APARTMENTS_CHANNEL, message)
    except Exception:
        logger.warning("Failed to publish apartment event %s", event_type, exc_info=True)


async def subscribe_to_apartments():
    """Выделенное соединение-подписчик (профиль — в `_subscriber`)."""
    return await _subscriber(APARTMENTS_CHANNEL)
