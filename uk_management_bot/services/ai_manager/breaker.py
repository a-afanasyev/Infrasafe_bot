"""Предохранитель ИИ-триажа: N сбоев подряд → окно без вызовов LLM.

Состояние — в Redis, а не в процессе: заявки создаются и ботом, и API
(разные процессы, разные пути dispatch) — per-process счётчики разошлись бы
и слали бы менеджеру дубли. Недоступный Redis трактуется как «закрыт»: LLM
вызываем, в лог — предупреждение; лишний вызов дешевле молчащего ИИ.
Синхронный клиент: триаж живёт в sync-пути dispatch (async — через
``to_thread``).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from uk_management_bot.config.settings import settings

logger = logging.getLogger(__name__)

FAIL_KEY = "ai:breaker:fail"
OPEN_KEY = "ai:breaker:open"
NOTIFIED_KEY = "ai:breaker:notified"
THRESHOLD = 3
OPEN_TTL = 600
FAIL_TTL = 600
_SOCKET_TIMEOUT = 3

_client: Optional[Any] = None


def _get_client():
    global _client
    if _client is None:
        import redis

        _client = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=_SOCKET_TIMEOUT,
            socket_timeout=_SOCKET_TIMEOUT,
        )
    return _client


def is_open() -> bool:
    """Открыт ли предохранитель (LLM не вызывать). Redis недоступен → False."""
    try:
        return _get_client().exists(OPEN_KEY) == 1
    except Exception as e:
        logger.warning("ai_manager.breaker: redis unavailable (%s), treating as closed", type(e).__name__)
        return False


def record_failure() -> bool:
    """Учесть сбой LLM. True — предохранитель только что открылся И это
    первое уведомление в окне (вызывающий шлёт менеджеру одно сообщение)."""
    try:
        client = _get_client()
        count = client.incr(FAIL_KEY)
        if client.ttl(FAIL_KEY) < 0:
            client.expire(FAIL_KEY, FAIL_TTL)
        if count < THRESHOLD:
            return False
        client.set(OPEN_KEY, "1", ex=OPEN_TTL)
        return bool(client.set(NOTIFIED_KEY, "1", nx=True, ex=OPEN_TTL))
    except Exception as e:
        logger.warning("ai_manager.breaker: redis unavailable (%s), failure not counted", type(e).__name__)
        return False


def record_success() -> None:
    try:
        _get_client().delete(FAIL_KEY)
    except Exception as e:
        logger.warning("ai_manager.breaker: redis unavailable (%s)", type(e).__name__)
