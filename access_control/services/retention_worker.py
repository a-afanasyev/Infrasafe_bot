"""Исполнитель retention-обязательств access-домена (AUD6-P1-5).

``expire_due_reviews`` (§9.5: тик «не реже раза в 10 с») и
``purge_expired_photos`` (§11: фото номера/автомобиля — 30 дней, персданные)
существовали с полным тест-покрытием, но БЕЗ единого прод-вызова: планировщика
в access_control не было вообще, и зелёный сьют маскировал невыполняемое
обязательство. Этот модуль — их единственный штатный исполнитель; живёт в
lifespan ``uk-access-api`` (см. ``app/main.py``): свой процесс, своя
runtime-роль ``access_app_rw`` (UPDATE на ``camera_events`` и INSERT в
``access_decisions``/audit у неё есть — обе таблицы в access-domain ACL).

Сессии — короткие, по одной на тик, через core ``SessionLocal`` из
``uk_management_bot.database.session``: своей фабрики у access_control нет,
все его роутеры используют ту же (`get_db`). Оба сервиса синхронные, поэтому
тик уходит в ``asyncio.to_thread`` — блокирующий SQL не должен стоять в
event loop API (класс проблемы AUD6-P2-01).

Ошибка одного тика логируется и НЕ убивает цикл: разовый сбой БД не повод
навсегда остановить retention до рестарта контейнера.
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

# §9.5: «не реже раза в 10 с». Константы, не env: интервалы — контракт ТЗ,
# а не ручка конфигурации; менять их надо через код и ревью.
REVIEW_TICK_SECONDS = 10.0
# Ретеншн меряется днями — часовой тик даёт максимум час опоздания на
# 30-дневном сроке и не создаёт заметной нагрузки (индексный SELECT + UPDATE).
PHOTO_TICK_SECONDS = 3600.0

_ENV_FLAG = "ACCESS_WORKERS_ENABLED"


def workers_enabled() -> bool:
    """Fail-open по умолчанию: воркер обязан работать, если его явно не сняли.

    Явное ``0/false/no/off`` выключает (тесты, разовые ops-запуски API без
    фоновой активности); любое другое значение или отсутствие переменной —
    включено. Осознанная противоположность fail-closed-гейтам доступа: здесь
    «забыли переменную» должно означать «обязательство исполняется».
    """
    raw = os.getenv(_ENV_FLAG)
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _review_tick() -> int:
    # Импорты внутри тика, а не модуля: SessionLocal создаётся при импорте
    # database.session из DATABASE_URL — модуль воркера должен оставаться
    # импортируемым в окружениях без БД (сбор тестов, инструменты).
    from uk_management_bot.database.session import SessionLocal

    from access_control.services.review_expiry import expire_due_reviews

    with SessionLocal() as db:
        # expire_due_reviews коммитит сам, по решению за раз (advisory lock).
        return expire_due_reviews(db)


def _photo_tick() -> int:
    from uk_management_bot.database.session import SessionLocal

    from access_control.services.photo_retention import purge_expired_photos

    with SessionLocal() as db:
        # Контракт purge_expired_photos: «коммит — на стороне вызывающего».
        count = purge_expired_photos(db)
        db.commit()
        return count


async def run_loop(
    name: str,
    tick,
    interval_seconds: float,
    stop: asyncio.Event,
) -> None:
    """Гонять ``tick`` в thread-pool каждые ``interval_seconds`` до ``stop``.

    Публичная и параметризованная — тесты гоняют её с малым интервалом и
    фейковым тиком, не трогая настоящие константы.
    """
    while not stop.is_set():
        try:
            processed = await asyncio.to_thread(tick)
            if processed:
                logger.info("retention worker %s: обработано %d", name, processed)
        except Exception:
            logger.warning(
                "retention worker %s: тик упал, цикл продолжается", name, exc_info=True
            )
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue  # обычный путь: интервал истёк, следующий тик


def start_retention_workers() -> tuple[list[asyncio.Task], asyncio.Event]:
    """Запустить оба цикла; вернуть (tasks, stop) для остановки на shutdown."""
    stop = asyncio.Event()
    tasks = [
        asyncio.create_task(
            run_loop("review-expiry", _review_tick, REVIEW_TICK_SECONDS, stop),
            name="access-retention-review-expiry",
        ),
        asyncio.create_task(
            run_loop("photo-retention", _photo_tick, PHOTO_TICK_SECONDS, stop),
            name="access-retention-photo",
        ),
    ]
    logger.info(
        "retention workers запущены: review-expiry каждые %ss, photo каждые %ss",
        REVIEW_TICK_SECONDS,
        PHOTO_TICK_SECONDS,
    )
    return tasks, stop


async def stop_retention_workers(
    tasks: list[asyncio.Task], stop: asyncio.Event
) -> None:
    """Кооперативная остановка: сигнал + дождаться выхода циклов.

    ``gather(return_exceptions=True)`` — shutdown не должен падать из-за
    последнего недобитого тика.
    """
    stop.set()
    await asyncio.gather(*tasks, return_exceptions=True)
