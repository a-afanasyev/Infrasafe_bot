"""П6c / AUD5-CODE-5 — job'ы планировщика не должны стопорить бота.

Планировщик живёт в процессе бота (`main.initialize_scheduler`), а его job'ы —
корутины на том же event loop, что и хендлеры. Пока внутри job'а крутился
sync-SQLAlchemy пакет (планирование недели, перебалансировка, автоназначение),
бот НЕ отвечал никому.

Проверяется не форма («вызван ли `to_thread`»), а само свойство: во время
job'а loop продолжает крутиться. Подменяется уровень НИЖЕ предмета пункта —
сервис, который job вызывает, а не сам job.

Второе требование пункта — сессия создаётся и закрывается ВНУТРИ рабочего
потока. `Session` не рассчитана на работу из двух потоков, и «открыли в
потоке, дописали в loop» — та же ошибка, только незаметная до продакшена.
"""
import asyncio
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from uk_management_bot.utils.shift_scheduler import ShiftScheduler, _ShiftReminder

SESSION_LOCAL_PATH = "uk_management_bot.utils.shift_scheduler.SessionLocal"
PLANNING_SVC_PATH = "uk_management_bot.utils.shift_scheduler.ShiftPlanningService"

MAIN_THREAD = None  # заполняется в тесте


def _make_scheduler(notification_service=None) -> ShiftScheduler:
    with patch("uk_management_bot.utils.shift_scheduler.AsyncIOScheduler"):
        return ShiftScheduler(notification_service=notification_service)


class _TrackedSession:
    """Сессия-дубль, помнящая, в каком потоке её создали и закрыли."""

    def __init__(self, log: list):
        self._log = log
        self.created_in = threading.get_ident()
        self.closed_in = None
        log.append(("session_created", self.created_in))

    def close(self):
        self.closed_in = threading.get_ident()
        self._log.append(("session_closed", self.closed_in))


@pytest.mark.asyncio
async def test_heavy_db_batch_does_not_freeze_the_event_loop():
    """Главный тест пункта: бот отвечает, пока планировщик считает пакет."""
    sched = _make_scheduler()

    slow_planning = MagicMock()

    def _slow(**kwargs):
        time.sleep(0.5)  # именно синхронный сон — так ведёт себя sync-ORM
        return {"total_created": 1}

    slow_planning.auto_create_shifts.side_effect = _slow

    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    beat = asyncio.create_task(heartbeat())
    try:
        with patch(SESSION_LOCAL_PATH, return_value=MagicMock()), \
                patch(PLANNING_SVC_PATH, return_value=slow_planning):
            await sched._auto_create_shifts()
    finally:
        beat.cancel()
        await asyncio.gather(beat, return_exceptions=True)

    assert ticks >= 5, (
        f"за 0.5s пакета loop успел сделать только {ticks} тиков — job считает "
        "прямо в event loop, и всё это время бот не отвечает хендлерам"
    )
    assert sched.task_stats["auto_create_shifts"]["success"] == 1


@pytest.mark.asyncio
async def test_session_is_opened_and_closed_in_the_same_worker_thread():
    """Сессия не должна пересекать границу потока ни одним концом."""
    sched = _make_scheduler()
    log: list = []
    sessions: list[_TrackedSession] = []

    def _factory():
        s = _TrackedSession(log)
        sessions.append(s)
        return s

    planning = MagicMock()
    planning.auto_create_shifts.return_value = {"total_created": 1}

    main_thread = threading.get_ident()
    with patch(SESSION_LOCAL_PATH, side_effect=_factory), \
            patch(PLANNING_SVC_PATH, return_value=planning):
        await sched._auto_create_shifts()

    assert len(sessions) == 1
    session = sessions[0]
    assert session.created_in != main_thread, (
        "сессия создана в event loop — значит db-фаза осталась на нём"
    )
    assert session.closed_in == session.created_in, (
        f"сессия открыта в потоке {session.created_in}, а закрыта в "
        f"{session.closed_in} — Session нельзя передавать между потоками"
    )


@pytest.mark.asyncio
async def test_notification_does_not_reuse_the_worker_thread_session():
    """Сетевая фаза идёт ПОСЛЕ db-фазы и на своей сессии.

    Раньше уведомление отправлялось внутри `try` job'а — на той же сессии,
    что и пакет. После выноса пакета в поток это стало бы использованием
    чужой сессии из другого потока.
    """
    sched = _make_scheduler()
    log: list = []
    sessions: list[_TrackedSession] = []

    def _factory():
        s = _TrackedSession(log)
        sessions.append(s)
        return s

    planning = MagicMock()
    planning.auto_create_shifts.return_value = {"total_created": 42}  # > 10 → уведомление

    notifier = MagicMock()
    notifier.send_manager_notification = AsyncMock(
        side_effect=lambda *a, **k: log.append(("notified", threading.get_ident()))
    )

    with patch(SESSION_LOCAL_PATH, side_effect=_factory), \
            patch(PLANNING_SVC_PATH, return_value=planning), \
            patch("uk_management_bot.utils.shift_scheduler.NotificationService",
                  return_value=notifier):
        sched._bot = object()  # включает уведомления без инжекта сервиса
        await sched._auto_create_shifts()

    kinds = [k for k, _ in log]
    assert "notified" in kinds, "уведомление не ушло"
    worker_session, notify_session = sessions[0], sessions[1]
    assert worker_session is not notify_session, (
        "сетевая фаза переиспользует сессию рабочего потока"
    )
    assert kinds.index("session_closed") < kinds.index("notified"), (
        "уведомление отправлено до закрытия сессии пакета — фазы не разделены"
    )


@pytest.mark.asyncio
async def test_reminders_leave_the_thread_as_dto_not_orm_rows():
    """Из потока наружу уходят плоские DTO, а не строки ORM.

    Дубль-строка имитирует поведение отсоединённого объекта: после `close()`
    обращение к полю падает. Если job отдаст ORM-объекты, тест покраснеет
    ровно там же, где прод — уже в сетевой фазе.
    """
    notifier = MagicMock()
    notifier.send_shift_reminder = AsyncMock()
    sched = _make_scheduler(notification_service=notifier)

    from datetime import timedelta
    from uk_management_bot.utils.datetime_utils import utc_now

    state = {"closed": False}
    starts_at = utc_now() + timedelta(hours=1)

    class _DetachedAfterClose:
        user_id = 7

        @property
        def start_time(self):
            if state["closed"]:
                raise RuntimeError("Instance is not bound to a Session (детач)")
            return starts_at

    session = MagicMock()
    session.close.side_effect = lambda: state.update(closed=True)
    session.query.return_value.join.return_value.filter.return_value.all.return_value = [
        _DetachedAfterClose()
    ]

    with patch(SESSION_LOCAL_PATH, return_value=session):
        await sched._notify_upcoming_shifts()

    notifier.send_shift_reminder.assert_awaited_once()
    passed = notifier.send_shift_reminder.await_args.kwargs["shift"]
    assert isinstance(passed, _ShiftReminder), (
        f"в сетевую фазу уехал {type(passed).__name__} из закрытой сессии"
    )
    assert passed.start_time == starts_at
    assert sched.task_stats["notify_upcoming"]["success"] == 1
