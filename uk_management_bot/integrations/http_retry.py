"""Retry helper for idempotent media-service HTTP calls (ARCH-03).

Медиа-вложения — SPOF: одиночный сетевой сбой или короткий рестарт
media-service иначе превращается в жёсткую ошибку у пользователя.
Идемпотентные GET безопасно ретраить с экспоненциальным backoff; запись
(upload, POST) здесь НЕ ретраится намеренно — это породило бы дубли файлов.
Явная деградация (graceful fallback) остаётся за вызывающим кодом.
"""

import asyncio
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# Дефолты подобраны под идемпотентные media-GET: 3 попытки, backoff 0.5→1.0→2.0с.
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_BASE = 0.5  # секунды
# Транзиентные gateway-ошибки media-service (рестарт/перегрузка) — ретраим.
# 500 не ретраим: чаще детерминированная ошибка приложения.
_RETRYABLE_STATUS = frozenset({502, 503, 504})


async def get_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    retries: int = DEFAULT_RETRIES,
    backoff_base: float = DEFAULT_BACKOFF_BASE,
    **kwargs: Any,
) -> httpx.Response:
    """GET `url` с ретраями транзиентных ошибок и backoff.

    Ретраит на `httpx.TransportError` (connect/read/timeout) и на
    502/503/504. Возвращает последний ответ (в т.ч. не-2xx), когда попытки
    исчерпаны; пробрасывает последнюю transport-ошибку, если все попытки
    упали на транспортном уровне. Только для идемпотентных GET.
    """
    if retries < 1:
        raise ValueError("retries must be >= 1")

    last_exc: Optional[httpx.TransportError] = None
    for attempt in range(retries):
        try:
            resp = await client.get(url, **kwargs)
        except httpx.TransportError as exc:
            last_exc = exc
            if attempt == retries - 1:
                logger.warning(
                    "media GET %s failed after %d attempts: %s", url, retries, exc
                )
                raise
            delay = backoff_base * (2 ** attempt)
            logger.info(
                "media GET %s transport error (attempt %d/%d), retry in %.1fs: %s",
                url, attempt + 1, retries, delay, exc,
            )
            await asyncio.sleep(delay)
            continue

        if resp.status_code in _RETRYABLE_STATUS and attempt < retries - 1:
            delay = backoff_base * (2 ** attempt)
            logger.info(
                "media GET %s -> %d (attempt %d/%d), retry in %.1fs",
                url, resp.status_code, attempt + 1, retries, delay,
            )
            await asyncio.sleep(delay)
            continue
        return resp

    # Недостижимо при retries >= 1 (последняя итерация всегда return/raise),
    # но оставлено для строгости.
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("get_with_retries exhausted without a response")
