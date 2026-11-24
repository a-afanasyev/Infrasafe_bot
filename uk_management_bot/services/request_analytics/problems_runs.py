"""Прогоны ИИ-разбора проблем: запуск в фоне, ограничения, хранение, статус.

Вызов модели идёт минуты, а edge режет запрос на 30 с — поэтому кнопка дашборда
ставит фоновую задачу (202) и опрашивает статус. Отчёт общий для площадки: его
видят все с доступом к аналитике, повторный запуск ради того же периода не нужен.

Ограничения — блок ``ai.problems`` конфига ИИ (страница «Правила ИИ»):
``manual_enabled``/``monthly_enabled``, ``rerun_cooldown_minutes`` (тот же период),
``min_interval_minutes`` (любые запуски), ``daily_limit`` (запусков по кнопке в сутки).

Состояние в Redis:
* ``ai:problems:running`` — один прогон на площадку одновременно (NX + TTL,
  значение — маркер прогона; снимает только свой прогон);
* ``ai:problems:last_start`` — время последнего старта (интервал по текущему конфигу);
* ``ai:problems:day:<дата>`` — счётчик запусков по кнопке за бизнес-сутки;
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
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.services.auto_manager.config import load_config
from uk_management_bot.utils.business_time import business_today

from .problems import ProblemsReport, analyze_problems

logger = logging.getLogger(__name__)

AUDIT_ACTION = "ai_problems_report"
RUNNING_KEY = "ai:problems:running"
#: Метка времени (epoch, с) последнего старта по кнопке — интервал сверяется с
#: ТЕКУЩИМ конфигом, смена `min_interval_minutes` действует сразу.
LAST_START_KEY = "ai:problems:last_start"
LAST_START_TTL_SECONDS = 2 * 24 * 3600
DAY_KEY = "ai:problems:day:{day}"
MONTHLY_KEY = "ai:problems:monthly:{month}"
FAILED_KEY = "ai:problems:failed:{first}:{last}"
FAILED_TTL_SECONDS = 600
MONTHLY_TTL_SECONDS = 40 * 24 * 3600
#: Сколько последних разборов (разных периодов) показывать на вкладке.
RECENT_LIMIT = 5

StartStatus = Literal["started", "disabled", "busy", "fresh", "interval", "limit"]

# Ссылки на фоновые задачи: без них asyncio может собрать задачу сборщиком мусора.
_tasks: set[asyncio.Task] = set()


@dataclass(frozen=True)
class StartOutcome:
    status: StartStatus
    #: Когда запуск снова станет возможен (для ``fresh``/``interval``/``limit``).
    retry_at: Optional[datetime] = None


class RedisUnavailable(RuntimeError):
    """Нет Redis — платный прогон не запускаем (fail-closed)."""


async def _redis():
    from uk_management_bot.services.redis_pubsub import get_pubsub_redis

    return await get_pubsub_redis()


def _failed_key(first: date, last: date) -> str:
    return FAILED_KEY.format(first=first.isoformat(), last=last.isoformat())


def _day_key() -> str:
    return DAY_KEY.format(day=business_today().isoformat())


def _session_factory():
    from uk_management_bot.database.session import AsyncSessionLocal

    return AsyncSessionLocal


def _now() -> datetime:
    return datetime.now(timezone.utc)


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


async def recent_reports(db: AsyncSession) -> list[dict]:
    """Последние разборы разных периодов: [{first, last, generated_at}], свежие первыми.

    Группировка по периоду в SQL: частые повторы одного периода не вытесняют остальные.
    """
    first_col = AuditLog.details["first"].as_string()
    last_col = AuditLog.details["last"].as_string()
    latest_id = func.max(AuditLog.id).label("latest_id")
    grouped = await db.execute(
        select(latest_id)
        .where(AuditLog.action == AUDIT_ACTION)
        .group_by(first_col, last_col)
        .order_by(latest_id.desc())
        .limit(RECENT_LIMIT)
    )
    ids = [row_id for (row_id,) in grouped.all()]
    if not ids:
        return []
    rows = await db.execute(
        select(AuditLog.id, first_col, last_col, AuditLog.details["generated_at"].as_string())
        .where(AuditLog.id.in_(ids))
        .order_by(AuditLog.id.desc())
    )
    return [{"first": first, "last": last, "generated_at": generated_at}
            for _id, first, last, generated_at in rows.all() if first and last]


def _fresh_until(report: Optional[dict], cooldown_minutes: int) -> Optional[datetime]:
    """До какого момента отчёт периода считается свежим (повтор запрещён)."""
    if report is None or cooldown_minutes <= 0:
        return None
    try:
        generated = datetime.fromisoformat(report["generated_at"])
    except (KeyError, TypeError, ValueError):
        return None
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    return generated + timedelta(minutes=cooldown_minutes)


async def run_report(
    session_factory, first: date, last: date, *, user_id: Optional[int], trigger: str,
) -> Optional[ProblemsReport]:
    """Собрать, спросить модель, сохранить. None — сбой (исключения не выходят)."""
    try:
        async with session_factory() as db:
            sla_hours = (await load_config(db))["sla_hours"]
            report = await analyze_problems(db, first, last, sla_hours, _now())
            if report is not None:
                await store_report(db, report, user_id=user_id, trigger=trigger)
            return report
    except Exception as exc:  # noqa: BLE001 — фон: только лог, без текста данных
        logger.error("ai_problems: прогон %s..%s упал: %s", first, last, type(exc).__name__)
        return None


async def _background(first: date, last: date, user_id: int, marker: str, day_key: str) -> None:
    report = None
    try:
        report = await run_report(_session_factory(), first, last, user_id=user_id, trigger="manual")
    finally:  # и при отмене задачи (остановка воркера): замок снять, сбой отметить
        try:
            redis = await _redis()
            if report is None:
                await redis.set(_failed_key(first, last), "1", ex=FAILED_TTL_SECONDS)
                # Неудачный прогон не съедает слот суток: иначе сбои модели запирают день.
                # Интервал остаётся — не даёт долбить кнопкой при сбоях.
                if int(await redis.get(day_key) or 0) > 0:
                    await redis.decr(day_key)
            await _release(redis, marker)
        except Exception as exc:  # noqa: BLE001 — замок сам истечёт по TTL
            logger.warning("ai_problems: Redis недоступен при завершении: %s", type(exc).__name__)


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _interval_until(redis, limits: dict) -> Optional[datetime]:
    """Когда истечёт интервал после последнего старта (по ТЕКУЩЕМУ конфигу)."""
    raw = await redis.get(LAST_START_KEY)
    if not raw or limits["min_interval_minutes"] <= 0:
        return None
    try:
        until = datetime.fromtimestamp(float(raw), timezone.utc) + timedelta(
            minutes=limits["min_interval_minutes"])
    except (TypeError, ValueError):
        return None
    return until if until > _now() else None


def _tomorrow_start() -> datetime:
    from uk_management_bot.utils.business_time import business_days_window

    tomorrow = business_today() + timedelta(days=1)
    return business_days_window(tomorrow, tomorrow)[0]


async def _check_limits(db: AsyncSession, redis, first: date, last: date, limits: dict,
                        day_key: str) -> Optional[StartOutcome]:
    """Проверки под замком, без побочных эффектов: отказ ничего не тратит."""
    fresh = _fresh_until(await latest_report(db, first, last), limits["rerun_cooldown_minutes"])
    if fresh is not None and fresh > _now():  # повтор: два клика подряд прошли первую проверку
        return StartOutcome("fresh", fresh)
    interval_until = await _interval_until(redis, limits)
    if interval_until is not None:
        return StartOutcome("interval", interval_until)
    if int(await redis.get(day_key) or 0) >= limits["daily_limit"]:
        return StartOutcome("limit", _tomorrow_start())
    return None


async def start_run(db: AsyncSession, first: date, last: date, user_id: int,
                    limits: dict) -> StartOutcome:
    """Поставить прогон в фон, если позволяют ограничения ``ai.problems``.

    Порядок: выключатель → свежесть отчёта (дёшево, без Redis) → замок → те же
    проверки под замком (замок сериализует воркеры) → и только при старте
    счётчик суток и метка интервала. Отказ не тратит ни слот, ни интервал.
    """
    if not limits["manual_enabled"]:
        return StartOutcome("disabled")
    fresh = _fresh_until(await latest_report(db, first, last), limits["rerun_cooldown_minutes"])
    if fresh is not None and fresh > _now():
        return StartOutcome("fresh", fresh)
    try:
        redis = await _redis()
        marker = await _acquire(redis, first, last, user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ai_problems: Redis недоступен: %s", type(exc).__name__)
        raise RedisUnavailable from exc
    if marker is None:
        return StartOutcome("busy")
    day_key = _day_key()
    try:
        refusal = await _check_limits(db, redis, first, last, limits, day_key)
        if refusal is not None:
            await _release(redis, marker)
            return refusal
        await redis.set(day_key, 0, nx=True, ex=LAST_START_TTL_SECONDS)  # TTL до первого INCR
        await redis.incr(day_key)
        await redis.set(LAST_START_KEY, str(_now().timestamp()), ex=LAST_START_TTL_SECONDS)
        await redis.delete(_failed_key(first, last))
    except Exception as exc:  # noqa: BLE001 — замок не оставляем висеть
        logger.warning("ai_problems: Redis сбой при старте: %s", type(exc).__name__)
        try:
            await _release(redis, marker)
        except Exception:  # noqa: BLE001 — истечёт по TTL
            pass
        raise RedisUnavailable from exc
    _spawn(_background(first, last, user_id, marker, day_key))
    return StartOutcome("started")


async def run_monthly(session_factory, first: date, last: date) -> Optional[ProblemsReport]:
    """Разбор месяца для автоотчёта: если включён, раз в месяц, под общим замком, без Redis — нет."""
    try:
        async with session_factory() as db:
            limits = (await load_config(db))["ai"]["problems"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("ai_problems: конфиг недоступен, месячный разбор пропущен: %s", type(exc).__name__)
        return None
    if not limits["monthly_enabled"]:
        logger.info("ai_problems: месячный разбор выключен в «Правилах ИИ»")
        return None
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
    report = None
    try:
        report = await run_report(session_factory, first, last, user_id=None, trigger="monthly")
        return report
    finally:
        try:
            if report is None:  # сбой — повторный запуск джобы в этом месяце попробует снова
                await redis.delete(month_key)
            await _release(redis, marker)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ai_problems: замок не снят: %s", type(exc).__name__)


async def run_status(db: AsyncSession, first: date, last: date, limits: dict) -> dict:
    """Для опроса дашбордом: прогон этого периода / другого (``busy``), сбой, отчёт,
    когда снова можно запускать и сколько запусков осталось на сегодня."""
    report = await latest_report(db, first, last)
    running = busy = failed = False
    waits: list[datetime] = []
    runs_left: Optional[int] = None
    fresh = _fresh_until(report, limits["rerun_cooldown_minutes"])
    if fresh is not None and fresh > _now():
        waits.append(fresh)
    try:
        redis = await _redis()
        marker = await redis.get(RUNNING_KEY)
        if marker:
            data = json.loads(marker)
            running = (data.get("first"), data.get("last")) == (first.isoformat(), last.isoformat())
            busy = not running
        failed = bool(await redis.get(_failed_key(first, last)))
        interval_until = await _interval_until(redis, limits)
        if interval_until:
            waits.append(interval_until)
        runs_left = max(0, limits["daily_limit"] - int(await redis.get(_day_key()) or 0))
        if runs_left == 0:
            waits.append(_tomorrow_start())
    except Exception as exc:  # noqa: BLE001 — статус best-effort: покажем хотя бы отчёт
        logger.warning("ai_problems: статус без Redis: %s", type(exc).__name__)
    return {"running": running, "busy": busy, "failed": failed and not running,
            "next_run_at": max(waits) if waits else None, "runs_left": runs_left,
            "report": report, "recent": await recent_reports(db)}
