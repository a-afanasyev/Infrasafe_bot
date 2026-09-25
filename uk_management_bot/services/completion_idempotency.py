"""Идемпотентность атомарного «Готово» исполнителя — Redis, без миграции.

Две сущности:

* **запись** по ключу клиента (`idempotency_key`, UUID) — стадия выполнения:
  ``uploaded`` (фото в media-service, заявка ещё не закрыта) или ``done``.
  Живёт сутки. Redis-ключ включает исполнителя и номер заявки, поэтому чужой
  или перенесённый на другую заявку ключ ничего не «воспроизводит»;
* **лок** на заявку (SET NX с токеном, TTL больше бюджета edge) — два
  параллельных «Готово» по одной заявке (двойной тап, повтор после таймаута
  клиента, пока первый ещё идёт) не грузят два фото.

**Fail-open при недоступном Redis — осознанно.** Цена отказа хранилища —
лишнее фото в фотоотчёте, и только в двух редких случаях (параллельный
повтор; повтор после сбоя шага workflow). Повтор после УСПЕХА и без Redis не
грузит второе фото: его ловит естественная идемпотентность в сервисе
(«заявка уже Выполнена этим исполнителем» проверяется ДО загрузки). Отказ же
(fail-closed) значит, что исполнитель на объекте не может закрыть работу, пока
лежит кэш, — это хуже видимого и удаляемого дубля.

В логах — только класс ошибки Redis (как `describe_http_error`), без текста
исключения: в нём может оказаться URL подключения.
"""
from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass
from typing import Optional

from uk_management_bot.services.redis_pubsub import get_pubsub_redis

logger = logging.getLogger(__name__)

STATE_UPLOADED = "uploaded"
STATE_DONE = "done"
_STATES = frozenset({STATE_UPLOADED, STATE_DONE})

RECORD_TTL_SECONDS = 24 * 3600
# Больше бюджета edge (30 с) с запасом на загрузку и транзакцию: лок не должен
# истечь посреди живого запроса, а упавший процесс не должен держать заявку.
LOCK_TTL_SECONDS = 90

_PREFIX = "exec_complete"

# compare-and-delete: удалить лок, только если он всё ещё наш.
_RELEASE_SCRIPT = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('del', KEYS[1]) else return 0 end"
)


async def get_redis():
    """Общий короткотаймаутный клиент API (2 с на connect/операцию)."""
    return await get_pubsub_redis()


@dataclass(frozen=True)
class Record:
    state: str
    media_id: Optional[int]


@dataclass(frozen=True)
class Lock:
    request_number: str
    token: Optional[str]
    acquired: bool
    # Redis недоступен: работаем без лока (fail-open, см. докстринг модуля).
    degraded: bool = False


def record_key(executor_id: int, request_number: str, key: str) -> str:
    return f"{_PREFIX}:rec:{executor_id}:{request_number}:{key}"


def _lock_key(request_number: str) -> str:
    return f"{_PREFIX}:lock:{request_number}"


def _warn(op: str, exc: BaseException) -> None:
    logger.warning("completion idempotency: Redis %s недоступен (%s) — продолжаем без него",
                   op, type(exc).__name__)


async def load(executor_id: int, request_number: str, key: str) -> Optional[Record]:
    try:
        raw = await (await get_redis()).get(record_key(executor_id, request_number, key))
    except Exception as exc:  # noqa: BLE001 — fail-open, см. докстринг
        _warn("get", exc)
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
        state, media_id = data["state"], data.get("media_id")
    except (ValueError, TypeError, KeyError):
        return None
    if state not in _STATES or (media_id is not None and not isinstance(media_id, int)):
        return None
    return Record(state=state, media_id=media_id)


async def save(executor_id: int, request_number: str, key: str,
               state: str, media_id: Optional[int]) -> None:
    value = json.dumps({"state": state, "media_id": media_id})
    try:
        await (await get_redis()).set(
            record_key(executor_id, request_number, key), value, ex=RECORD_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 — fail-open
        _warn("set", exc)


async def acquire_lock(request_number: str) -> Lock:
    token = secrets.token_hex(16)
    try:
        ok = await (await get_redis()).set(
            _lock_key(request_number), token, nx=True, ex=LOCK_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 — fail-open
        _warn("lock", exc)
        return Lock(request_number, None, acquired=True, degraded=True)
    return Lock(request_number, token if ok else None, acquired=bool(ok))


async def release_lock(lock: Lock) -> None:
    """Снять СВОЙ лок. Чужой (наш истёк по TTL, его взял другой) не трогаем.

    Сравнение и удаление — один EVAL: GET и DEL отдельными командами оставляли
    окно, в котором наш лок истекал, доставался другому запросу и удалялся нами.
    """
    if not lock.acquired or lock.token is None:
        return
    try:
        await (await get_redis()).eval(
            _RELEASE_SCRIPT, 1, _lock_key(lock.request_number), lock.token)
    except Exception as exc:  # noqa: BLE001 — лок истечёт по TTL
        _warn("unlock", exc)
