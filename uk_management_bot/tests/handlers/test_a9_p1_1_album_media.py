"""A9-P1-1 (+A9-P3-15): альбом фото молча терялся во всех FSM-сборщиках медиа.

Два дефекта в одной цепочке:
1. ``ThrottlingMiddleware`` (0,5 с) отбрасывал все части альбома, кроме первой
   (тест — ``middlewares/test_throttling.py``).
2. Сборщики делали ``get_data → append → update_data``: апдейты альбома
   обрабатываются конкурентно (aiogram ``handle_as_tasks``), и с Redis-storage
   (JSON-сериализация, каждая операция — сетевой ``await``) каждый хендлер читал
   пустой список → lost update, в состоянии оставался один файл.

``_RedisLikeStorage`` воспроизводит ровно эти свойства прод-Redis: данные
сериализуются (никаких общих ссылок на список, как у MemoryStorage — там
``append`` мутировал сохранённый список и прятал гонку) и каждая операция
уступает event loop.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from typing import Any, Dict, Mapping
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from uk_management_bot.utils.fsm_media import (
    BOT_MEDIA_MAX_FILES,
    append_fsm_media,
)
from uk_management_bot.utils.helpers import get_text

ALBUM_SIZE = 5


class _RedisLikeStorage(MemoryStorage):
    """MemoryStorage с семантикой RedisStorage: сериализация + yield на I/O."""

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        await asyncio.sleep(0)
        await super().set_data(key, json.loads(json.dumps(dict(data))))

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        await asyncio.sleep(0)
        return json.loads(json.dumps(await super().get_data(key)))


def _state(user_id: int = 5001) -> FSMContext:
    key = StorageKey(bot_id=1, chat_id=user_id, user_id=user_id)
    return FSMContext(storage=_RedisLikeStorage(), key=key)


def _photo_message(idx: int, *, user_id: int = 5001, file_size: int = 100_000,
                   media_group_id: str | None = "album-1"):
    msg = MagicMock()
    msg.from_user.id = user_id
    msg.message_id = 1000 + idx
    msg.media_group_id = media_group_id
    photo = MagicMock()
    photo.file_id = f"photo-{idx}"
    photo.file_size = file_size
    msg.photo = [photo]
    msg.video = None
    msg.document = None
    msg.text = None
    msg.answer = AsyncMock()
    return msg


def _album(n: int = ALBUM_SIZE, **kw):
    return [_photo_message(i, **kw) for i in range(n)]


# ---------------------------------------------------------------------------
# Общий хелпер дозаписи
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_helper_concurrent_appends_keep_every_item():
    state = _state()
    results = await asyncio.gather(
        *(append_fsm_media(state, "media_files", f"f{i}") for i in range(ALBUM_SIZE))
    )
    data = await state.get_data()
    assert sorted(data["media_files"]) == [f"f{i}" for i in range(ALBUM_SIZE)]
    assert all(r.added for r in results)
    assert sorted(r.count for r in results) == list(range(1, ALBUM_SIZE + 1))


@pytest.mark.asyncio
async def test_helper_limit_rejects_overflow_atomically():
    state = _state()
    results = await asyncio.gather(
        *(append_fsm_media(state, "media_files", f"f{i}") for i in range(BOT_MEDIA_MAX_FILES + 3))
    )
    data = await state.get_data()
    assert len(data["media_files"]) == BOT_MEDIA_MAX_FILES
    assert sum(r.added for r in results) == BOT_MEDIA_MAX_FILES
    assert all(r.count == BOT_MEDIA_MAX_FILES for r in results if not r.added)


@pytest.mark.asyncio
async def test_helper_notifies_limit_once_per_album():
    state = _state()
    results = await asyncio.gather(
        *(append_fsm_media(state, "media_files", f"f{i}", media_group_id="g1")
          for i in range(BOT_MEDIA_MAX_FILES + 3))
    )
    rejected = [r for r in results if not r.added]
    assert len(rejected) == 3
    assert sum(r.notify for r in rejected) == 1


@pytest.mark.asyncio
async def test_helper_notifies_every_single_message_over_limit():
    state = _state()
    for i in range(BOT_MEDIA_MAX_FILES):
        await append_fsm_media(state, "media_files", f"f{i}")
    extra = [await append_fsm_media(state, "media_files", "x") for _ in range(2)]
    assert [(r.added, r.notify) for r in extra] == [(False, True), (False, True)]


@pytest.mark.asyncio
async def test_helper_keeps_album_order_by_message_id():
    """Замок сериализует, но части встают в очередь в порядке прихода задач —
    итоговый список обязан идти в порядке отправки (message_id)."""
    state = _state()
    shuffled = [3, 0, 4, 1, 2]
    await asyncio.gather(
        *(append_fsm_media(state, "media_files", f"f{i}",
                           media_group_id="g1", message_id=100 + i)
          for i in shuffled)
    )
    assert (await state.get_data())["media_files"] == [f"f{i}" for i in range(5)]


@pytest.mark.asyncio
async def test_helper_single_messages_go_to_the_end():
    state = _state()
    await append_fsm_media(state, "media_files", "late", message_id=200)
    await append_fsm_media(state, "media_files", "early", message_id=100)
    assert (await state.get_data())["media_files"] == ["late", "early"]


@pytest.mark.asyncio
async def test_create_album_shuffled_arrival_keeps_send_order():
    from uk_management_bot.handlers.requests import create

    state = _state()
    album = _album()
    shuffled = [album[i] for i in (4, 1, 0, 3, 2)]
    with patch.object(create, "_get_user_language", AsyncMock(return_value="ru")):
        await asyncio.gather(*(create.process_media(m, state) for m in shuffled))

    assert (await state.get_data())["media_files"] == [f"photo-{i}" for i in range(ALBUM_SIZE)]


@pytest.mark.asyncio
async def test_helper_keeps_other_fsm_keys():
    state = _state()
    await state.update_data(description="течёт кран", media_files=["old"])
    await append_fsm_media(state, "media_files", "new")
    data = await state.get_data()
    assert data["description"] == "течёт кран"
    assert data["media_files"] == ["old", "new"]


# ---------------------------------------------------------------------------
# Четыре сборщика: альбом из 5 апдейтов конкурентно → 5 файлов
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_request_album_keeps_all_files():
    from uk_management_bot.handlers.requests import create

    state = _state()
    with patch.object(create, "_get_user_language", AsyncMock(return_value="ru")):
        await asyncio.gather(*(create.process_media(m, state) for m in _album()))

    assert len((await state.get_data())["media_files"]) == ALBUM_SIZE


@pytest.mark.asyncio
async def test_inspector_album_keeps_all_files():
    from uk_management_bot.handlers import inspector_requests as insp

    state = _state()
    with patch.object(insp, "_lang", AsyncMock(return_value="ru")):
        await asyncio.gather(*(insp.inspector_media(m, state) for m in _album()))

    assert len((await state.get_data())["media_files"]) == ALBUM_SIZE


@contextmanager
def _fake_db_scope(_db=None):
    yield MagicMock()


@pytest.mark.asyncio
async def test_executor_completion_album_keeps_all_files():
    from uk_management_bot.handlers.requests import executor as ex

    state = _state()
    await state.update_data(executor_request_number="260923-001")
    with patch.object(ex, "_db_scope", _fake_db_scope), \
         patch.object(ex, "get_user_language", return_value="ru"):
        await asyncio.gather(
            *(ex.executor_collect_completion_media(m, state) for m in _album())
        )

    media = (await state.get_data())["completion_media"]
    assert [m["file_id"] for m in sorted(media, key=lambda m: m["file_id"])] == [
        f"photo-{i}" for i in range(ALBUM_SIZE)
    ]


@pytest.mark.asyncio
async def test_return_media_album_keeps_all_files():
    from uk_management_bot.handlers import request_acceptance as ra

    state = _state()
    await asyncio.gather(*(ra.save_return_media(m, state, language="ru") for m in _album()))

    assert len((await state.get_data())["return_media"]) == ALBUM_SIZE


# ---------------------------------------------------------------------------
# Лимит: лишние файлы не молча, а с понятным ответом
# ---------------------------------------------------------------------------

LIMIT_TEXT = get_text("requests.media_limit_reached", language="ru", max=BOT_MEDIA_MAX_FILES)


def _answered_texts(messages) -> list[str]:
    return [call.args[0] for m in messages for call in m.answer.await_args_list]


@pytest.mark.asyncio
async def test_create_album_over_limit_answers_limit_text():
    from uk_management_bot.handlers.requests import create

    state = _state()
    album = _album(BOT_MEDIA_MAX_FILES + 2)
    with patch.object(create, "_get_user_language", AsyncMock(return_value="ru")):
        await asyncio.gather(*(create.process_media(m, state) for m in album))

    assert len((await state.get_data())["media_files"]) == BOT_MEDIA_MAX_FILES
    # один ответ о лимите на альбом, а не на каждый лишний файл
    assert _answered_texts(album).count(LIMIT_TEXT) == 1


@pytest.mark.asyncio
async def test_create_single_messages_over_limit_each_answered():
    """Одиночные сообщения (без media_group_id) — ответ на каждое, как раньше."""
    from uk_management_bot.handlers.requests import create

    state = _state()
    msgs = [_photo_message(i, media_group_id=None) for i in range(BOT_MEDIA_MAX_FILES + 2)]
    with patch.object(create, "_get_user_language", AsyncMock(return_value="ru")):
        for m in msgs:
            await create.process_media(m, state)

    assert _answered_texts(msgs).count(LIMIT_TEXT) == 2


@pytest.mark.asyncio
async def test_second_album_over_limit_is_answered_again():
    """Дедуп — по media_group_id: следующий альбом сверх лимита снова получает ответ."""
    from uk_management_bot.handlers.requests import create

    state = _state()
    first = _album(BOT_MEDIA_MAX_FILES + 1, media_group_id="album-1")
    second = _album(2, media_group_id="album-2")
    with patch.object(create, "_get_user_language", AsyncMock(return_value="ru")):
        await asyncio.gather(*(create.process_media(m, state) for m in first))
        await asyncio.gather(*(create.process_media(m, state) for m in second))

    assert _answered_texts(first).count(LIMIT_TEXT) == 1
    assert _answered_texts(second).count(LIMIT_TEXT) == 1


@pytest.mark.asyncio
async def test_executor_completion_media_is_limited():
    """A9-P3-15: у фото завершения исполнителя лимита не было вовсе."""
    from uk_management_bot.handlers.requests import executor as ex

    state = _state()
    album = _album(BOT_MEDIA_MAX_FILES + 3)
    with patch.object(ex, "_db_scope", _fake_db_scope), \
         patch.object(ex, "get_user_language", return_value="ru"):
        await asyncio.gather(*(ex.executor_collect_completion_media(m, state) for m in album))

    assert len((await state.get_data())["completion_media"]) == BOT_MEDIA_MAX_FILES
    assert _answered_texts(album).count(LIMIT_TEXT) == 1


def test_limit_text_is_localized_in_both_languages():
    ru = get_text("requests.media_limit_reached", language="ru", max=BOT_MEDIA_MAX_FILES)
    uz = get_text("requests.media_limit_reached", language="uz", max=BOT_MEDIA_MAX_FILES)
    assert str(BOT_MEDIA_MAX_FILES) in ru and str(BOT_MEDIA_MAX_FILES) in uz
    assert ru != uz
    assert "{" not in ru and "{" not in uz


# ---------------------------------------------------------------------------
# A9-P3-15: размер файла и формат счётчика в create.py
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_rejects_oversized_file_by_real_size():
    from uk_management_bot.handlers.requests import create

    state = _state()
    msg = _photo_message(0, file_size=25 * 1024 * 1024, media_group_id=None)
    with patch.object(create, "_get_user_language", AsyncMock(return_value="ru")):
        await create.process_media(msg, state)

    assert (await state.get_data()).get("media_files", []) == []
    msg.answer.assert_awaited_once()
    assert msg.answer.await_args.args[0] == get_text("requests.file_too_large", language="ru")


@pytest.mark.asyncio
async def test_create_file_added_counter_is_formatted():
    from uk_management_bot.handlers.requests import create

    state = _state()
    msg = _photo_message(0, media_group_id=None)
    with patch.object(create, "_get_user_language", AsyncMock(return_value="ru")):
        await create.process_media(msg, state)

    text = msg.answer.await_args.args[0]
    assert "{" not in text
    assert f"1/{BOT_MEDIA_MAX_FILES}" in text


# ---------------------------------------------------------------------------
# A9-P3-15: callback.answer ДО долгого скачивания медиа
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_executor_view_media_answers_callback_before_download():
    from uk_management_bot.handlers.requests import executor as ex

    callback = MagicMock()
    callback.data = "executor_view_media_260923-001"
    callback.from_user.id = 777
    callback.answer = AsyncMock()
    callback.message.answer = AsyncMock()
    callback.message.answer_photo = AsyncMock()
    callback.message.answer_media_group = AsyncMock()

    answered_before_download: list[bool] = []

    async def _download(media_id):
        answered_before_download.append(callback.answer.await_count > 0)
        return (b"\xff\xd8jpeg", "image/jpeg")

    media_client = MagicMock()
    media_client.download_media_file = AsyncMock(side_effect=_download)
    request = MagicMock()
    request.media_files = [{"media_id": 42, "type": "photo"}]
    service = MagicMock()
    service.get_request_by_number.return_value = request
    service.get_user_by_telegram_id.return_value = MagicMock()

    with patch.object(ex, "RequestHandlerService", return_value=service), \
         patch.object(ex, "get_user_language", return_value="ru"), \
         patch.object(ex, "has_request_access_sync", return_value=True), \
         patch.object(ex, "get_media_client", return_value=media_client):
        await ex.executor_view_media(callback, _db=MagicMock())

    assert answered_before_download == [True]
    callback.message.answer_photo.assert_awaited_once()
    callback.answer.assert_awaited_once()
