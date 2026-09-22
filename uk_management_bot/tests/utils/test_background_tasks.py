"""A9-P3-9: fire-and-forget задачи держатся сильной ссылкой до завершения.

Event loop хранит задачи СЛАБЫМИ ссылками (`asyncio.all_tasks` — WeakSet).
Задача, ждущая future, на который больше никто не ссылается, образует цикл
task↔future и собирается GC посреди работы («Task was destroyed but it is
pending!») — уведомление молча не уходит.
"""
import asyncio
import gc
import weakref
from unittest.mock import MagicMock, patch


async def test_spawn_keeps_task_alive_until_done():
    from uk_management_bot.utils import background_tasks

    loop = asyncio.get_running_loop()
    finished = []

    async def _job():
        # future, на который ссылается ТОЛЬКО кадр корутины
        await loop.create_future()

    async def _gated_job(gate):
        await gate
        finished.append(True)

    ref = weakref.ref(background_tasks.spawn(_job()))
    await asyncio.sleep(0)
    gc.collect()
    assert ref() is not None, "задачу собрал GC до завершения"
    assert ref() in background_tasks.pending_tasks()
    ref().cancel()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert ref() is None or ref() not in background_tasks.pending_tasks()

    gate = loop.create_future()
    task = background_tasks.spawn(_gated_job(gate))
    gate.set_result(None)
    await task
    await asyncio.sleep(0)
    assert finished == [True]
    assert task not in background_tasks.pending_tasks(), "ссылка не снята по завершении"


async def test_notify_user_send_task_survives_gc():
    """notify_user: задача отправки не собирается GC, пока отправка висит."""
    from uk_management_bot.services.notification_service import NotificationService

    user = MagicMock(telegram_id=555)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    svc = NotificationService(db, bot=MagicMock())

    state = {}

    async def _hanging_send(bot, tg_id, text):
        fut = asyncio.get_running_loop().create_future()
        state["fut_ref"] = weakref.ref(fut)
        await fut
        return True

    with patch(
        "uk_management_bot.services.notification_service.service.send_to_user",
        side_effect=_hanging_send,
    ):
        svc.notify_user(1, "T", "B")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        gc.collect()
        fut = state["fut_ref"]()
        assert fut is not None, "задачу отправки собрал GC до завершения"
        fut.set_result(None)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

