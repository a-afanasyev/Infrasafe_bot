"""A9-P3-9: канон fire-and-forget задач — сильная ссылка до завершения.

Event loop держит задачи только СЛАБЫМИ ссылками (`asyncio.all_tasks()` —
WeakSet). Задача, ждущая future, на который больше никто не ссылается
(типичный сетевой вызов), образует цикл task↔future, и GC может собрать её
посреди работы: отправка молча не происходит, в логе — лишь «Task was
destroyed but it is pending!». Документация asyncio прямо требует хранить
ссылку на такие задачи — этот модуль и есть то место.

Использование: `spawn(coro)` вместо голого `loop.create_task(coro)`, когда
результат задачи никто не ждёт.
"""
from __future__ import annotations

import asyncio
from typing import Coroutine, Optional

# Модульный реестр: задача живёт в нём ровно до done-callback.
_background_tasks: set[asyncio.Task] = set()


def spawn(coro: Coroutine, *, name: Optional[str] = None) -> asyncio.Task:
    """Запустить корутину фоном на текущем running loop и удержать задачу.

    Бросает `RuntimeError`, если running loop нет — как и `asyncio.create_task`.
    Исход (ошибка/отмена) — забота вызывающего: свой done-callback он вешает
    на возвращённую задачу. Неразобранное исключение asyncio залогирует сам
    («Task exception was never retrieved») — здесь оно не глотается.
    """
    task = asyncio.get_running_loop().create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def pending_tasks() -> frozenset[asyncio.Task]:
    """Снимок удерживаемых задач (для тестов/диагностики)."""
    return frozenset(_background_tasks)
