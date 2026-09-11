"""`Request.media_files` хранит три формы элементов (telegram file_id строкой,
dict с file_id, dict с media_id медиа-сервиса — пишет api/routes/media_proxy.py).
Единственный разборщик и отправитель — services/request_media_entries.py:
файлы медиа-сервиса скачиваются байтами (токен медиа-сервиса ≠ токен бота,
его file_id боту не годится), группы режутся по лимиту Telegram (10)."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import BufferedInputFile, InputMediaDocument, InputMediaPhoto, InputMediaVideo

from uk_management_bot.services.request_media_entries import (
    MediaEntry,
    build_input_media,
    parse_media_entries,
    send_media_entries,
)


# ── parse_media_entries ──────────────────────────────────────────────


def test_parse_accepts_all_three_shapes_and_json_string():
    raw = json.dumps([
        "AgAC-plain",
        {"file_id": "AgAC-dict", "type": "video"},
        {"media_id": 42, "type": "document"},
    ])
    assert parse_media_entries(raw) == [
        MediaEntry(kind="photo", file_id="AgAC-plain"),
        MediaEntry(kind="video", file_id="AgAC-dict"),
        MediaEntry(kind="document", media_id=42),
    ]


def test_parse_list_input_and_unknown_type_defaults_to_photo():
    assert parse_media_entries([{"media_id": 7, "type": "weird"}]) == [
        MediaEntry(kind="photo", media_id=7),
    ]


@pytest.mark.parametrize("raw", [None, "", [], "not json", "{}", 5, [None, "", {}, {"media_id": "x"}, 3]])
def test_parse_garbage_yields_nothing(raw):
    assert parse_media_entries(raw) == []


# ── build_input_media ────────────────────────────────────────────────


def _client(downloads: dict[int, tuple[bytes, str] | None]):
    client = MagicMock()
    client.download_media_file = AsyncMock(side_effect=lambda media_id: downloads.get(media_id))
    return client


@pytest.mark.asyncio
async def test_build_mixes_file_ids_and_downloaded_bytes():
    entries = [
        MediaEntry(kind="photo", file_id="AgAC-1"),
        MediaEntry(kind="photo", media_id=42),
        MediaEntry(kind="video", media_id=43),
    ]
    client = _client({42: (b"\xff\xd8jpeg", "image/jpeg"), 43: (b"\x00mp4", "video/mp4")})

    items = await build_input_media(entries, client)

    assert [type(i) for i in items] == [InputMediaPhoto, InputMediaPhoto, InputMediaVideo]
    assert items[0].media == "AgAC-1"
    assert isinstance(items[1].media, BufferedInputFile)
    assert items[1].media.filename == "media_42.jpg"
    assert isinstance(items[2].media, BufferedInputFile)
    assert items[2].media.filename == "media_43.mp4"


@pytest.mark.asyncio
async def test_build_skips_failed_download_keeps_rest():
    entries = [MediaEntry(kind="photo", media_id=1), MediaEntry(kind="document", file_id="AgAC-doc")]
    items = await build_input_media(entries, _client({1: None}))
    assert len(items) == 1
    assert isinstance(items[0], InputMediaDocument)


@pytest.mark.asyncio
async def test_build_without_media_client_sends_only_file_ids():
    entries = [MediaEntry(kind="photo", media_id=1), MediaEntry(kind="photo", file_id="AgAC-1")]
    items = await build_input_media(entries, None)
    assert [i.media for i in items] == ["AgAC-1"]


# ── send_media_entries ───────────────────────────────────────────────


def _message():
    msg = MagicMock()
    for name in ("answer_photo", "answer_video", "answer_document", "answer_media_group"):
        setattr(msg, name, AsyncMock())
    return msg


@pytest.mark.asyncio
async def test_send_single_photo_uses_answer_photo_not_group():
    msg = _message()
    sent = await send_media_entries(msg, [MediaEntry(kind="photo", file_id="AgAC-1")], None)
    assert sent == 1
    msg.answer_photo.assert_awaited_once_with(photo="AgAC-1", caption=None)
    msg.answer_media_group.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_single_video_and_document_use_matching_method():
    msg = _message()
    await send_media_entries(msg, [MediaEntry(kind="video", file_id="v")], None)
    await send_media_entries(msg, [MediaEntry(kind="document", file_id="d")], None)
    msg.answer_video.assert_awaited_once_with(video="v", caption=None)
    msg.answer_document.assert_awaited_once_with(document="d", caption=None)


@pytest.mark.asyncio
async def test_send_twelve_items_chunks_by_telegram_limit():
    msg = _message()
    entries = [MediaEntry(kind="photo", file_id=f"f{i}") for i in range(12)]
    sent = await send_media_entries(msg, entries, None, first_caption="Фото 1/12")
    assert sent == 12
    assert msg.answer_media_group.await_count == 2
    first, second = (c.kwargs["media"] for c in msg.answer_media_group.await_args_list)
    assert len(first) == 10 and len(second) == 2
    assert first[0].caption == "Фото 1/12"
    assert first[1].caption is None


@pytest.mark.asyncio
async def test_send_eleven_items_last_chunk_goes_as_single():
    msg = _message()
    entries = [MediaEntry(kind="photo", file_id=f"f{i}") for i in range(11)]
    assert await send_media_entries(msg, entries, None) == 11
    msg.answer_media_group.assert_awaited_once()
    msg.answer_photo.assert_awaited_once_with(photo="f10", caption=None)


@pytest.mark.asyncio
async def test_send_nothing_when_all_entries_unresolvable():
    msg = _message()
    sent = await send_media_entries(msg, [MediaEntry(kind="photo", media_id=1)], _client({1: None}))
    assert sent == 0
    msg.answer_photo.assert_not_awaited()
    msg.answer_media_group.assert_not_awaited()
