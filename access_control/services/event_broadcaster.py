"""Брокер live-трансляции событий доступа для WS-панели охраны (§9.6, §11).

Абстракция publish/subscribe для доставки PD-safe событий доступа подключённым
операторам охраны в реальном времени (критерий §15.13):

* ``InProcessBroker`` (по умолчанию) — in-process asyncio-брокер. Для пилота
  ``uk-access-api`` работает в ОДНОМ процессе, поэтому события, опубликованные
  ingestion/lifecycle, доходят до WS-подписчиков того же процесса.
* ``RedisBroker`` (по флагу ``ACCESS_EVENT_BROKER=redis``) — Redis pub/sub для
  нескольких воркеров/процессов.

ВАЖНО (ограничение пилота): при запуске НЕСКОЛЬКИХ воркеров (gunicorn/uvicorn
``--workers > 1`` или несколько контейнеров) in-process брокер доставит событие
только подписчикам своего процесса — WS-клиент на другом воркере его не увидит.
Для many-worker прода ОБЯЗАТЕЛЕН Redis-брокер (см. ``RedisBroker``).

PD-safe (§11): ``AccessEventMessage`` намеренно НЕ содержит полного номера, кода
или URL фото — только исход, зону/точку, направление, время и маскированный
номер (последние символы). Полные ПД не покидают БД через WS-канал.

``publish`` — СИНХРОННАЯ функция: её безопасно вызывать из синхронного
ingestion/lifecycle (sync ``Session``) ПОСЛЕ ``commit``. Доставка подписчику
выполняется на его event loop через ``call_soon_threadsafe`` (кросс-поточно).
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import threading
from typing import Protocol

logger = logging.getLogger(__name__)

# Канал Redis pub/sub для событий доступа (используется RedisBroker).
ACCESS_EVENT_CHANNEL = "access:events"


@dataclasses.dataclass(frozen=True)
class AccessEventMessage:
    """Иммутабельное PD-safe событие доступа для WS-клиентов (§9.6, §11).

    Намеренно БЕЗ полного номера/фото: только исход (decision/status/reason),
    зона/точка, направление, время и маскированный номер (хвост).
    """

    decision: str
    status: str
    reason: str | None = None
    zone_id: int | None = None
    gate_id: int | None = None
    direction: str | None = None
    occurred_at: str | None = None
    plate_masked: str | None = None
    kind: str = "access_event"

    def to_payload(self) -> dict:
        """Сериализуемый dict для отправки клиенту. ``type`` — тег фрейма."""
        return {
            "type": self.kind,
            "decision": self.decision,
            "status": self.status,
            "reason": self.reason,
            "zone_id": self.zone_id,
            "gate_id": self.gate_id,
            "direction": self.direction,
            "occurred_at": self.occurred_at,
            "plate_masked": self.plate_masked,
        }

    @classmethod
    def from_payload(cls, payload: dict) -> "AccessEventMessage":
        return cls(
            decision=payload.get("decision", ""),
            status=payload.get("status", ""),
            reason=payload.get("reason"),
            zone_id=payload.get("zone_id"),
            gate_id=payload.get("gate_id"),
            direction=payload.get("direction"),
            occurred_at=payload.get("occurred_at"),
            plate_masked=payload.get("plate_masked"),
        )


def mask_plate(normalized: str | None, *, tail: int = 2) -> str | None:
    """Маскировать номер для WS (§11): раскрыть только ``tail`` последних символов.

    ``None``/пустой → ``None``. Начало заменяется ``*`` (минимум один символ
    маски), хвост сохраняется. Полный номер в WS-канал не попадает.
    """
    if not normalized:
        return None
    if len(normalized) <= tail:
        return "*" * len(normalized)
    return "*" * (len(normalized) - tail) + normalized[-tail:]


# ───────────────────────── абстракция брокера ────────────────────────────────


class Subscription(Protocol):
    """Подписка на поток событий доступа."""

    async def get(self) -> AccessEventMessage: ...

    def close(self) -> None: ...


class EventBroker(Protocol):
    """Брокер publish/subscribe событий доступа."""

    def publish(self, message: AccessEventMessage) -> None: ...

    def subscribe(self) -> Subscription: ...


# ───────────────────────── in-process реализация ─────────────────────────────


class _InProcessSubscription:
    """Подписка in-process брокера, привязанная к event loop подписчика.

    Создаётся внутри async WS-обработчика → захватывает его running loop.
    ``_offer`` может вызываться из ЛЮБОГО потока (sync publish), поэтому кладёт
    сообщение в очередь через ``call_soon_threadsafe``.
    """

    def __init__(self, broker: "InProcessBroker") -> None:
        self._broker = broker
        self._queue: asyncio.Queue[AccessEventMessage] = asyncio.Queue()
        self._loop = asyncio.get_running_loop()

    def _offer(self, message: AccessEventMessage) -> None:
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, message)
        except RuntimeError:
            # Loop закрыт/остановлен — подписчик уходит, тихо игнорируем.
            logger.debug("drop event for closed subscriber loop")

    async def get(self) -> AccessEventMessage:
        return await self._queue.get()

    def close(self) -> None:
        self._broker._remove(self)


class InProcessBroker:
    """In-process asyncio-брокер (дефолт пилота, один процесс).

    Потокобезопасен: ``publish`` (sync, из ingestion-потока) и ``subscribe``
    (async, из WS-обработчика) синхронизируются через ``threading.Lock``.
    """

    def __init__(self) -> None:
        self._subscribers: set[_InProcessSubscription] = set()
        self._lock = threading.Lock()

    def publish(self, message: AccessEventMessage) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for sub in subscribers:
            sub._offer(message)

    def subscribe(self) -> _InProcessSubscription:
        sub = _InProcessSubscription(self)
        with self._lock:
            self._subscribers.add(sub)
        return sub

    def _remove(self, sub: _InProcessSubscription) -> None:
        with self._lock:
            self._subscribers.discard(sub)

    def reset(self) -> None:
        with self._lock:
            self._subscribers.clear()


# ───────────────────────── Redis pub/sub реализация ──────────────────────────


class _RedisSubscription:
    """Подписка Redis pub/sub: async-чтение канала ``ACCESS_EVENT_CHANNEL``."""

    def __init__(self, url: str, channel: str) -> None:
        import redis.asyncio as aioredis

        self._client = aioredis.from_url(url)
        self._pubsub = self._client.pubsub()
        self._channel = channel
        self._subscribed = False

    async def _ensure(self) -> None:
        if not self._subscribed:
            await self._pubsub.subscribe(self._channel)
            self._subscribed = True

    async def get(self) -> AccessEventMessage:
        await self._ensure()
        while True:
            raw = await self._pubsub.get_message(
                ignore_subscribe_messages=True, timeout=None
            )
            if raw is None or raw.get("type") != "message":
                continue
            data = raw["data"]
            if isinstance(data, (bytes, bytearray)):
                data = data.decode("utf-8")
            return AccessEventMessage.from_payload(json.loads(data))

    def close(self) -> None:
        # Закрытие async-ресурсов выполняется best-effort; WS-обработчик
        # завершает соединение, GC закроет соединения Redis.
        try:
            asyncio.get_running_loop().create_task(self._pubsub.aclose())
        except RuntimeError:
            pass


class RedisBroker:
    """Redis pub/sub брокер для many-worker прода (флаг ``ACCESS_EVENT_BROKER=redis``).

    ``publish`` — СИНХРОННЫЙ (через ``redis.Redis``), чтобы вызываться из
    sync-ingestion без event loop. Подписка — async (``redis.asyncio``).
    """

    def __init__(self, url: str, channel: str = ACCESS_EVENT_CHANNEL) -> None:
        import redis

        self._url = url
        self._channel = channel
        self._sync_client = redis.Redis.from_url(url)

    def publish(self, message: AccessEventMessage) -> None:
        try:
            self._sync_client.publish(
                self._channel, json.dumps(message.to_payload())
            )
        except Exception:  # noqa: BLE001 — доставка событий не должна ронять домен
            logger.exception("redis publish failed (event dropped)")

    def subscribe(self) -> _RedisSubscription:
        return _RedisSubscription(self._url, self._channel)


# ───────────────────────── singleton/фабрика ─────────────────────────────────

_broker: EventBroker | None = None
_broker_lock = threading.Lock()


def get_broker() -> EventBroker:
    """Вернуть процессный singleton брокера, создав по конфигурации при первом вызове.

    ``ACCESS_EVENT_BROKER=redis`` → ``RedisBroker`` (требует REDIS_URL); иначе
    in-process (дефолт пилота).
    """
    global _broker
    if _broker is None:
        with _broker_lock:
            if _broker is None:
                _broker = _build_broker()
    return _broker


def _build_broker() -> EventBroker:
    import os

    kind = os.getenv("ACCESS_EVENT_BROKER", "memory").strip().lower()
    if kind == "redis":
        from uk_management_bot.config.settings import settings

        url = settings.REDIS_PUBSUB_URL_RESOLVED
        logger.info("access event broker: redis (%s)", url)
        return RedisBroker(url)
    logger.info("access event broker: in-process (single-worker pilot)")
    return InProcessBroker()


def set_broker(broker: EventBroker | None) -> None:
    """Подменить singleton брокера (для тестов/DI)."""
    global _broker
    with _broker_lock:
        _broker = broker


def reset_broker() -> None:
    """Сбросить singleton: чистый in-process брокер без подписчиков (тесты)."""
    set_broker(InProcessBroker())
