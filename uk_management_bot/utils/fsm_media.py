"""Атомарная дозапись медиа в FSM-состояние (A9-P1-1).

Единственная точка, через которую FSM-сборщики медиа бота (создание заявки,
инспектор, фото завершения исполнителя, медиа возврата на доработку) добавляют
файл в список и где живёт лимит числа файлов.

Зачем: альбом из N фото Telegram присылает N апдейтами за миллисекунды, а
aiogram обрабатывает апдейты конкурентно (``handle_as_tasks``). Прежний
``get_data → append → update_data`` в каждом хендлере — read-modify-write
через Redis-storage: все части альбома читали пустой список, и в состоянии
выживал один файл (lost update).

KNOWN CONSTRAINT (как SEC-09 у throttling.py): сериализация — процессный
``asyncio.Lock`` на ключ FSM (bot, chat, user, …). Этого достаточно, потому что
все апдейты одного пользователя обрабатывает единственный воркер бота
(docs/development/known-constraints.md). При нескольких воркерах нужен
распределённый замок/атомарная операция в Redis — Redis-storage aiogram хранит
данные одним JSON-значением, частичного RPUSH в нём нет.
"""
from __future__ import annotations

import asyncio
import weakref
from dataclasses import dataclass
from typing import Any, Optional

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey

# Лимит файлов на один FSM-сборщик. Прежде жил литералом «5» в create/inspector
# и отсутствовал у фото завершения исполнителя (A9-P3-15).
BOT_MEDIA_MAX_FILES = 5

# Слабые ссылки: замок живёт, пока его держит/ждёт хотя бы один хендлер, —
# словарь не растёт с числом пользователей.
_locks: "weakref.WeakValueDictionary[StorageKey, asyncio.Lock]" = weakref.WeakValueDictionary()


@dataclass(frozen=True)
class MediaAppendResult:
    added: bool
    count: int  # число файлов в списке после попытки
    # Сообщать ли пользователю о лимите: для альбома — один раз на
    # media_group_id, а не на каждый лишний файл; одиночным — всегда.
    notify: bool = False


def _lock_for(key: StorageKey) -> asyncio.Lock:
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


def _insert_position(
    ids: list[Optional[int]], media_group_id: Optional[str], message_id: Optional[int]
) -> int:
    """Позиция вставки: с хвоста назад, мимо уже записанных частей с большим
    message_id (message_id в чате монотонен). Одиночные и без id — в конец."""
    pos = len(ids)
    if media_group_id is None or message_id is None:
        return pos
    while pos > 0 and ids[pos - 1] is not None and ids[pos - 1] > message_id:
        pos -= 1
    return pos


async def append_fsm_media(
    state: FSMContext,
    data_key: str,
    item: Any,
    *,
    media_group_id: Optional[str] = None,
    message_id: Optional[int] = None,
    limit: int = BOT_MEDIA_MAX_FILES,
) -> MediaAppendResult:
    """Добавить ``item`` в список ``data_key`` FSM-данных, если лимит не исчерпан.

    Порядок: замок сериализует части альбома в порядке прихода задач, а не
    отправки, поэтому часть альбома встаёт по ``message_id`` (служебный
    параллельный список ``<data_key>_msg_ids``; формат самого ``data_key`` не
    меняется — его читают сохранение заявки и др.). Одиночные — в конец.
    """
    async with _lock_for(state.key):
        data = await state.get_data()
        current = list(data.get(data_key) or [])
        if len(current) < limit:
            ids_key = f"{data_key}_msg_ids"
            ids = list(data.get(ids_key) or [])
            if len(ids) != len(current):  # список собран без id (до A9-P1-1)
                ids = [None] * len(current)
            pos = _insert_position(ids, media_group_id, message_id)
            await state.update_data({
                data_key: [*current[:pos], item, *current[pos:]],
                ids_key: [*ids[:pos], message_id, *ids[pos:]],
            })
            return MediaAppendResult(added=True, count=len(current) + 1)

        if media_group_id is None:
            return MediaAppendResult(added=False, count=len(current), notify=True)
        notified_key = f"{data_key}_limit_notified_group"
        if data.get(notified_key) == media_group_id:
            return MediaAppendResult(added=False, count=len(current), notify=False)
        await state.update_data({notified_key: media_group_id})
        return MediaAppendResult(added=False, count=len(current), notify=True)
