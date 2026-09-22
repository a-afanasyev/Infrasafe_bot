"""Таймауты синхронных Redis-клиентов access-домена (A9-P3-23).

Sync Redis зовётся на пути ответа (anti-replay nonce device-auth, счётчики
неверных гостевых кодов, publish live-событий). Без таймаутов Redis на паузе
держал запрос, поток anyio и соединение БД до TCP-таймаута ОС. С таймаутами
ошибка приходит за секунды, и вызывающий отвечает по своему канону
(device-auth — fail-closed 503).
"""
from __future__ import annotations

REDIS_SOCKET_TIMEOUT_SECONDS = 2.0
REDIS_CONNECT_TIMEOUT_SECONDS = 2.0


def sync_redis_from_url(url: str):
    """``redis.Redis`` с таймаутами чтения/подключения."""
    import redis

    return redis.Redis.from_url(
        url,
        socket_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
        socket_connect_timeout=REDIS_CONNECT_TIMEOUT_SECONDS,
    )
