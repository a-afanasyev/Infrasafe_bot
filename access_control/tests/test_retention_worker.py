"""AUD6-P1-5: у retention-сервисов появился исполнитель — фиксируем его контракт.

До этого файла ``expire_due_reviews`` и ``purge_expired_photos`` были покрыты
тестами, но не вызывались ниоткуда в проде: тесты доказывали корректность
механизма, существование исполнителя не проверял никто. Здесь проверяется
именно исполнитель: цикл тикает, ошибка тика не убивает цикл, выключатель
работает, lifespan приложения реально запускает и останавливает воркеры.
"""
import asyncio

import pytest

from access_control.services import retention_worker as rw


# ── run_loop: тикает, переживает ошибки, останавливается ────────────────────


@pytest.mark.asyncio
async def test_loop_ticks_repeatedly():
    calls = []
    stop = asyncio.Event()

    def tick() -> int:
        calls.append(1)
        if len(calls) >= 3:
            stop.set()
        return 0

    await asyncio.wait_for(rw.run_loop("t", tick, 0.01, stop), timeout=5)
    assert len(calls) >= 3


@pytest.mark.asyncio
async def test_tick_error_does_not_kill_loop():
    """Разовый сбой БД не должен навсегда останавливать retention."""
    calls = []
    stop = asyncio.Event()

    def tick() -> int:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("db down")
        stop.set()
        return 0

    await asyncio.wait_for(rw.run_loop("t", tick, 0.01, stop), timeout=5)
    assert len(calls) >= 2, "после упавшего тика цикл обязан продолжиться"


@pytest.mark.asyncio
async def test_stop_event_ends_loop_promptly():
    stop = asyncio.Event()

    def tick() -> int:
        stop.set()  # остановка, запрошенная во время тика
        return 0

    await asyncio.wait_for(rw.run_loop("t", tick, 3600, stop), timeout=5)
    # Дошли сюда без таймаута — цикл не заснул на весь interval после stop.


# ── start/stop: пара задач и кооперативное завершение ───────────────────────


@pytest.mark.asyncio
async def test_start_creates_both_workers_and_stop_joins_them(monkeypatch):
    monkeypatch.setattr(rw, "_review_tick", lambda: 0)
    monkeypatch.setattr(rw, "_photo_tick", lambda: 0)
    monkeypatch.setattr(rw, "REVIEW_TICK_SECONDS", 0.01)
    monkeypatch.setattr(rw, "PHOTO_TICK_SECONDS", 0.01)

    tasks, stop = rw.start_retention_workers()
    assert len(tasks) == 2
    await asyncio.sleep(0.05)  # дать циклам поработать
    await asyncio.wait_for(rw.stop_retention_workers(tasks, stop), timeout=5)
    assert all(t.done() for t in tasks)


# ── выключатель ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, True),  # отсутствие переменной = обязательство исполняется
        ("1", True),
        ("true", True),
        ("anything-else", True),
        ("0", False),
        ("false", False),
        ("no", False),
        ("off", False),
        ("  OFF  ", False),
    ],
)
def test_workers_enabled_flag(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("ACCESS_WORKERS_ENABLED", raising=False)
    else:
        monkeypatch.setenv("ACCESS_WORKERS_ENABLED", raw)
    assert rw.workers_enabled() is expected


# ── lifespan приложения ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lifespan_starts_and_stops_workers(monkeypatch):
    """Проверяем сам провод: create_app → lifespan → воркеры живут → shutdown.

    Тики подменяются целиком (моки БД тут ни к чему — тело тиков покрывают
    test_review_expiry/test_photo_retention; предмет ЭТОГО теста — что
    lifespan их запускает и глушит).
    """
    from access_control.app.main import create_app

    review_calls = []
    monkeypatch.setattr(rw, "_review_tick", lambda: review_calls.append(1) or 0)
    monkeypatch.setattr(rw, "_photo_tick", lambda: 0)
    monkeypatch.setattr(rw, "REVIEW_TICK_SECONDS", 0.01)
    monkeypatch.setenv("ACCESS_WORKERS_ENABLED", "true")

    app = create_app()
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.05)
    assert review_calls, "внутри lifespan воркер обязан тикать"

    running = [
        t for t in asyncio.all_tasks()
        if t.get_name().startswith("access-retention-") and not t.done()
    ]
    assert not running, "после выхода из lifespan воркеров быть не должно"


@pytest.mark.asyncio
async def test_lifespan_respects_disabled_flag(monkeypatch):
    from access_control.app.main import create_app

    called = []
    monkeypatch.setattr(rw, "_review_tick", lambda: called.append(1) or 0)
    monkeypatch.setattr(rw, "REVIEW_TICK_SECONDS", 0.01)
    monkeypatch.setenv("ACCESS_WORKERS_ENABLED", "false")

    app = create_app()
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.03)
    assert not called, "с выключенным флагом фоновой активности быть не должно"
