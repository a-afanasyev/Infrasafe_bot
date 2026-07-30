"""AUD6-P2-05: межворкерная координация work-reports (Dockerfile.api: --workers 2).

Module-level троттлы и кэши живут в КАЖДОМ воркере свои: ревокация в воркере A
не сбрасывала кэш B — отозванный отчёт оставался в ПУБЛИЧНОЙ ленте до
троттл+TTL (комментарий «потолок ровно один — троттл» был верен только для
одного воркера); reconcile выполнялся по разу на воркер за окно, расширяя
гонку AUD6-P2-04.

Redis уже в стеке (pubsub) — здесь два примитива поверх него. Оба с явной
деградацией: при недоступном Redis возвращается None, и вызывающий падает на
прежнее процессное поведение (честно задокументированный потолок вместо
молчаливого вранья).
"""

import logging
from typing import Optional

from uk_management_bot.services.redis_pubsub import get_pubsub_redis

logger = logging.getLogger(__name__)

_EPOCH_KEY = "work_reports:public_cache_epoch"
_RECONCILE_SLOT_KEY = "work_reports:reconcile_slot"


async def cache_epoch() -> Optional[int]:
    """Текущая эпоха публичного кэша; None = Redis недоступен.

    Кэш-запись валидна, только если её эпоха совпадает с текущей — INCR эпохи
    инвалидирует записи всех воркеров разом. При None кэш валидируется только
    по TTL (прежнее поведение одного воркера).
    """
    try:
        redis = await get_pubsub_redis()
        value = await redis.get(_EPOCH_KEY)
        return int(value) if value is not None else 0
    except Exception as e:
        logger.debug("cache_epoch: redis недоступен (%s)", e)
        return None


async def bump_cache_epoch() -> Optional[int]:
    """Инвалидировать публичный кэш во всех воркерах (ревокация/unpublish/reject).

    Возвращает новую эпоху либо None при недоступном Redis (тогда чужие
    воркеры доедят свой кэш по TTL — прежний потолок).
    """
    try:
        redis = await get_pubsub_redis()
        return int(await redis.incr(_EPOCH_KEY))
    except Exception as e:
        logger.warning(
            "bump_cache_epoch: redis недоступен (%s) — кэш других воркеров истечёт по TTL", e
        )
        return None


async def try_acquire_reconcile_slot(ttl_seconds: int) -> Optional[bool]:
    """SET NX EX: один reconcile на окно НА ВСЕ воркеры.

    True — слот наш; False — окно уже занято (этим или другим воркером);
    None — Redis недоступен, вызывающий использует процессный троттл.
    """
    try:
        redis = await get_pubsub_redis()
        return bool(await redis.set(_RECONCILE_SLOT_KEY, "1", nx=True, ex=ttl_seconds))
    except Exception as e:
        logger.debug("reconcile_slot: redis недоступен (%s)", e)
        return None
