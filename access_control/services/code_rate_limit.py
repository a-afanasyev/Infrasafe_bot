"""Rate-limit / lockout одноразовых кодов (§9.3).

Счётчики НЕВЕРНЫХ попыток погашения кода в скользящем окне. Блок при ≥5 неверных
за 10 минут по КАЖДОМУ из ключей: operator account, source IP, хэш кода. Сам код в
ключ НЕ кладётся (только HMAC-хэш) и НЕ логируется (§9.3, §11).

Абстракция стора по образцу ``device_auth.NonceStore``: in-memory дефолт (пилот/
один воркер/тесты) + Redis (прод/несколько воркеров — общий счётчик). Backend
выбирается env ``ACCESS_NONCE_BACKEND`` (как у nonce-store): ``memory`` (дефолт) |
``redis``; при ``redis`` и недоступном Redis — FATAL (без тихой деградации, M2).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Protocol

logger = logging.getLogger(__name__)

# Порог и окно блокировки (§9.3): ≥5 неверных за 10 минут.
FAILURE_THRESHOLD = 5
FAILURE_WINDOW_SECONDS = 600


class FailureCounterStore(Protocol):
    """Счётчик неверных попыток в окне. PD-safe ключи (без сырого кода)."""

    def record_failure(
        self, key: str, window_seconds: int
    ) -> int:  # pragma: no cover - Protocol
        """Зафиксировать неверную попытку по ключу; вернуть число попыток в окне."""
        ...

    def failure_count(
        self, key: str, window_seconds: int
    ) -> int:  # pragma: no cover - Protocol
        """Текущее число неверных попыток по ключу в окне (без инкремента."""
        ...


class InMemoryFailureStore:
    """In-memory счётчик (дефолт пилота/тестов): процесс-локальный, скользящее окно.

    Для одного процесса backend пилота достаточно. Несколько воркеров —
    ``RedisFailureStore`` (общий счётчик), иначе лимит обходится сменой воркера.
    """

    def __init__(self) -> None:
        self._events: dict[str, list[float]] = {}

    def _prune(self, key: str, window_seconds: int, now: float) -> list[float]:
        cutoff = now - window_seconds
        kept = [t for t in self._events.get(key, []) if t > cutoff]
        if kept:
            self._events[key] = kept
        else:
            self._events.pop(key, None)
        # Лёгкая защита от неограниченного роста словаря.
        if len(self._events) > 8192:
            self._events = {
                k: [t for t in v if t > cutoff]
                for k, v in self._events.items()
                if any(t > cutoff for t in v)
            }
        return kept

    def record_failure(self, key: str, window_seconds: int) -> int:
        now = time.monotonic()
        kept = self._prune(key, window_seconds, now)
        kept.append(now)
        self._events[key] = kept
        return len(kept)

    def failure_count(self, key: str, window_seconds: int) -> int:
        now = time.monotonic()
        return len(self._prune(key, window_seconds, now))


class RedisFailureStore:
    """Счётчик на Redis (прод/несколько воркеров): фиксированное окно через INCR+EX.

    Первый инкремент ключа выставляет TTL = окно: окно фиксированное от первой
    неверной попытки, что для блокировки кода достаточно (§9.3).
    """

    def __init__(self, client) -> None:
        self._client = client

    def _key(self, key: str) -> str:
        return f"ac:codefail:{key}"

    def record_failure(self, key: str, window_seconds: int) -> int:
        rkey = self._key(key)
        count = int(self._client.incr(rkey))
        if count == 1:
            self._client.expire(rkey, window_seconds)
        return count

    def failure_count(self, key: str, window_seconds: int) -> int:
        raw = self._client.get(self._key(key))
        return int(raw) if raw is not None else 0


_default_store: FailureCounterStore | None = None


def get_failure_store() -> FailureCounterStore:
    """Синглтон счётчика. Backend — env ``ACCESS_NONCE_BACKEND`` (как у nonce-store).

    Явный env — высший приоритет: ``redis`` → ``RedisFailureStore`` из
    ``settings.REDIS_URL``; ``memory`` → ``InMemoryFailureStore``. При ОТСУТСТВИИ
    переменной дефолт зависит от ``settings.DEBUG`` (SEC-02/аудит #4, fail-closed):
    в проде (``DEBUG=false``) — ``redis``, в dev/тестах — ``memory``. Раньше дефолт
    был безусловно ``memory``: на multi-worker проде lockout-счётчик становился
    process-local и обходился сменой воркера. При ``redis`` и недоступном Redis —
    FATAL (RuntimeError), БЕЗ тихого отката на in-memory (M2).
    """
    global _default_store
    if _default_store is not None:
        return _default_store
    backend = os.getenv("ACCESS_NONCE_BACKEND")
    if backend is None:
        from uk_management_bot.config.settings import settings
        backend = "memory" if settings.DEBUG else "redis"
    backend = backend.lower()
    if backend == "redis":
        try:
            import redis  # type: ignore

            from uk_management_bot.config.settings import settings

            client = redis.Redis.from_url(settings.REDIS_URL)
            client.ping()
            _default_store = RedisFailureStore(client)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "redis code-rate-limit store недоступен (%s) — FATAL, тихий откат "
                "на in-memory запрещён (лимит не должен молча обходиться)", exc
            )
            raise RuntimeError(
                "ACCESS_NONCE_BACKEND=redis, но Redis для rate-limit кодов недоступен; "
                "тихий откат на in-memory запрещён (M2, §9.3)."
            ) from exc
    else:
        _default_store = InMemoryFailureStore()
    return _default_store


def reset_failure_store(store: FailureCounterStore | None = None) -> None:
    """Сбросить/подменить синглтон счётчика (для тестов изоляции)."""
    global _default_store
    _default_store = store


def rate_limit_keys(
    *, operator_user_id: int, source_ip: str | None, code_hash: str
) -> list[str]:
    """Ключи лимита (§9.3): operator account + source IP + хэш кода.

    Сам код в ключ не попадает — только его HMAC-хэш (§9.3 «код не в логах»).
    apartment известен лишь после успешной проверки, поэтому в лимите неверных
    попыток не участвует.
    """
    return [
        f"op:{operator_user_id}",
        f"ip:{source_ip or 'unknown'}",
        f"code:{code_hash}",
    ]


def is_blocked(store: FailureCounterStore, keys: list[str]) -> bool:
    """Заблокирован ли хотя бы один ключ (≥ порога неверных за окно, §9.3)."""
    return any(
        store.failure_count(k, FAILURE_WINDOW_SECONDS) >= FAILURE_THRESHOLD
        for k in keys
    )


def record_failures(store: FailureCounterStore, keys: list[str]) -> bool:
    """Зафиксировать неверную попытку по всем ключам; вернуть «теперь заблокирован»."""
    blocked = False
    for k in keys:
        count = store.record_failure(k, FAILURE_WINDOW_SECONDS)
        if count >= FAILURE_THRESHOLD:
            blocked = True
    return blocked
