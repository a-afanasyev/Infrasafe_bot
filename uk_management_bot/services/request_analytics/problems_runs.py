"""Прогоны ИИ-разбора проблем: запуск в фоне, блокировка, хранение, статус.

Вызов модели идёт минуты, а edge режет запрос на 30 с — поэтому кнопка дашборда
ставит фоновую задачу (202) и опрашивает статус. Состояние в Redis:

* ``ai:problems:running`` — один прогон на площадку одновременно (NX + TTL,
  значение — маркер прогона; снимает только свой прогон);
* ``ai:problems:day:<дата>`` — суточный бюджет ручных прогонов;
* ``ai:problems:monthly:<YYYY-MM>`` — ежемесячный разбор не чаще раза в месяц;
* ``ai:problems:failed:<период>`` — последний прогон периода не удался;
* результат — строка ``audit_logs`` (``ai_problems_report``), история без миграции.

Платный вызов fail-closed: без Redis модель не зовётся ни с кнопки (503), ни из
ежемесячного отчёта (там — только CSV).
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Literal, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.services.auto_manager.config import load_config
from uk_management_bot.utils.business_time import business_today

from .problems import ProblemsReport, analyze_problems

logger = logging.getLogger(__name__)

AUDIT_ACTION = "ai_problems_report"
RUNNING_KEY = "ai:problems:running"
DAY_KEY = "ai:problems:day:{day}"
MONTHLY_KEY = "ai:problems:monthly:{month}"
FAILED_KEY = "ai:problems:failed:{first}:{last}"
FAILED_TTL_SECONDS = 600
MONTHLY_TTL_SECONDS = 40 * 24 * 3600

StartResult = Literal["started", "busy", "limit"]

# Ссылки на фоновые задачи: без них asyncio может собрать задачу сборщиком мусора.
_tasks: set[asyncio.Task] = set()


class RedisUnavailable(RuntimeError):
    """Нет Redis — платный прогон не запускаем (fail-closed)."""


async def _redis():
    from uk_management_bot.services.redis_pubsub import get_pubsub_redis

    return await get_pubsub_redis()


def _failed_key(first: date, last: date) -> str:
    return FAILED_KEY.format(first=first.isoformat(), last=last.isoformat())


def _session_factory():
    from uk_management_bot.database.session import AsyncSessionLocal

    return AsyncSessionLocal


def _lock_ttl() -> int:
    # Сбор дайджеста + вызов модели + запись; замок переживёт прогон с запасом.
    return int(settings.AI_PROBLEMS_LLM_TIMEOUT) + 180


async def _acquire(redis, first: date, last: date, user_id: Optional[int]) -> Optional[str]:
    """Взять замок прогона → маркер (снимать им же) или None, если занято."""
    marker = json.dumps({"first": first.isoformat(), "last": last.isoformat(),
                         "user_id": user_id, "run": uuid.uuid4().hex})
    return marker if await redis.set(RUNNING_KEY, marker, nx=True, ex=_lock_ttl()) else None


async def _release(redis, marker: str) -> None:
    # ponytail: get+delete не атомарны; окно — миллисекунды после TTL. Lua CAS, если станет важно.
    if await redis.get(RUNNING_KEY) == marker:
        await redis.delete(RUNNING_KEY)


async def store_report(db: AsyncSession, report: ProblemsReport, *,
                       user_id: Optional[int], trigger: str) -> None:
    db.add(AuditLog(user_id=user_id, action=AUDIT_ACTION,
                    details={**report.to_json(), "trigger": trigger}))
    await db.commit()


async def latest_report(db: AsyncSession, first: date, last: date) -> Optional[dict]:
    """Последний сохранённый отчёт ровно за этот период (или None)."""
    rows = await db.execute(
        select(AuditLog.details)
        .where(
            AuditLog.action == AUDIT_ACTION,
            AuditLog.details["first"].as_string() == first.isoformat(),
            AuditLog.details["last"].as_string() == last.isoformat(),
        )
        .order_by(AuditLog.id.desc())
        .limit(1)
    )
    details = rows.scalar_one_or_none()
    return details if isinstance(details, dict) else None


async def run_report(
    session_factory, first: date, last: date, *, user_id: Optional[int], trigger: str,
) -> Optional[ProblemsReport]:
    """Собрать, спросить модель, сохранить. None — сбой (исключения не выходят)."""
    try:
        async with session_factory() as db:
            sla_hours = (await load_config(db))["sla_hours"]
            report = await analyze_problems(db, first, last, sla_hours, datetime.now(timezone.utc))
            if report is not None:
                await store_report(db, report, user_id=user_id, trigger=trigger)
            return report
    except Exception as exc:  # noqa: BLE001 — фон: только лог, без текста данных
        logger.error("ai_problems: прогон %s..%s упал: %s", first, last, type(exc).__name__)
        return None


async def _background(first: date, last: date, user_id: int, marker: str) -> None:
    report = None
    try:
        report = await run_report(_session_factory(), first, last, user_id=user_id, trigger="manual")
    finally:  # и при отмене задачи (остановка воркера): замок снять, сбой отметить
        try:
            redis = await _redis()
            if report is None:
                await redis.set(_failed_key(first, last), "1", ex=FAILED_TTL_SECONDS)
            await _release(redis, marker)
        except Exception as exc:  # noqa: BLE001 — замок сам истечёт по TTL
            logger.warning("ai_problems: Redis недоступен при завершении: %s", type(exc).__name__)


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def start_run(first: date, last: date, user_id: int) -> StartResult:
    """Поставить прогон в фон; ``busy`` — уже идёт, ``limit`` — исчерпан бюджет суток."""
    try:
        redis = await _redis()
        marker = await _acquire(redis, first, last, user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ai_problems: Redis недоступен: %s", type(exc).__name__)
        raise RedisUnavailable from exc
    if marker is None:
        return "busy"
    try:
        day_key = DAY_KEY.format(day=business_today().isoformat())
        used = await redis.incr(day_key)
        if used == 1:
            await redis.expire(day_key, 2 * 24 * 3600)
        if used > settings.AI_PROBLEMS_DAILY_LIMIT:
            await _release(redis, marker)
            return "limit"
        await redis.delete(_failed_key(first, last))
    except Exception as exc:  # noqa: BLE001 — замок не оставляем висеть
        logger.warning("ai_problems: Redis сбой при старте: %s", type(exc).__name__)
        try:
            await _release(redis, marker)
        except Exception:  # noqa: BLE001 — истечёт по TTL
            pass
        raise RedisUnavailable from exc
    _spawn(_background(first, last, user_id, marker))
    return "started"


async def run_monthly(session_factory, first: date, last: date) -> Optional[ProblemsReport]:
    """Разбор месяца для автоотчёта: раз в месяц, под общим замком, без Redis — нет."""
    try:
        redis = await _redis()
        month_key = MONTHLY_KEY.format(month=first.isoformat()[:7])
        if not await redis.set(month_key, "1", nx=True, ex=MONTHLY_TTL_SECONDS):
            logger.info("ai_problems: разбор за %s уже делали", first.isoformat()[:7])
            return None
        marker = await _acquire(redis, first, last, None)
    except Exception as exc:  # noqa: BLE001 — платный вызов fail-closed
        logger.warning("ai_problems: месячный разбор без Redis пропущен: %s", type(exc).__name__)
        return None
    if marker is None:
        await redis.delete(month_key)  # занято ручным прогоном — повторит следующий запуск
        logger.info("ai_problems: месячный разбор пропущен — идёт другой прогон")
        return None
    try:
        return await run_report(session_factory, first, last, user_id=None, trigger="monthly")
    finally:
        try:
            await _release(redis, marker)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ai_problems: замок не снят: %s", type(exc).__name__)


async def run_status(db: AsyncSession, first: date, last: date) -> dict:
    """Для опроса дашбордом: прогон этого периода / другого (``busy``), сбой, отчёт."""
    running = busy = failed = False
    try:
        redis = await _redis()
        marker = await redis.get(RUNNING_KEY)
        if marker:
            data = json.loads(marker)
            running = (data.get("first"), data.get("last")) == (first.isoformat(), last.isoformat())
            busy = not running
        failed = bool(await redis.get(_failed_key(first, last)))
    except Exception as exc:  # noqa: BLE001 — статус best-effort: покажем хотя бы отчёт
        logger.warning("ai_problems: статус без Redis: %s", type(exc).__name__)
    return {"running": running, "busy": busy, "failed": failed and not running,
            "report": await latest_report(db, first, last)}
