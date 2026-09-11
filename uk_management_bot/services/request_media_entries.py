"""Элементы `Request.media_files` → отправка в Telegram.

Колонка хранит три формы (см. комментарий в `database/models/request.py`):
telegram file_id строкой, dict с `file_id`, dict с `media_id` медиа-сервиса
(пишет `api/routes/media_proxy.py` при загрузке через дашборд/TWA).

Файлы медиа-сервиса отправляются БАЙТАМИ, а не его `telegram_file_id`:
медиа-сервис живёт под собственным бот-токеном (`MEDIA_BOT_TOKEN`), и его
file_id для основного бота не годится.

Единственная точка, где знают о лимите Telegram на медиагруппу (2–10):
один элемент уходит `answer_photo/video/document`, больше — чанками по 10.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal, Optional, Sequence

from aiogram.types import (
    BufferedInputFile,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)

logger = logging.getLogger(__name__)

MediaKind = Literal["photo", "video", "document"]
_KINDS: tuple[MediaKind, ...] = ("photo", "video", "document")
TELEGRAM_MEDIA_GROUP_MAX = 10

_INPUT_MEDIA_BY_KIND = {
    "photo": InputMediaPhoto,
    "video": InputMediaVideo,
    "document": InputMediaDocument,
}
_EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
}


@dataclass(frozen=True)
class MediaEntry:
    kind: MediaKind
    file_id: Optional[str] = None
    media_id: Optional[int] = None


def parse_media_entries(raw: Any) -> list[MediaEntry]:
    """Разобрать сырое значение колонки; мусор молча пропускается."""
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(raw, list):
        return []
    entries: list[MediaEntry] = []
    for item in raw:
        entry = _parse_item(item)
        if entry is not None:
            entries.append(entry)
    return entries


def _parse_item(item: Any) -> Optional[MediaEntry]:
    if isinstance(item, str):
        return MediaEntry(kind="photo", file_id=item) if item else None
    if not isinstance(item, dict):
        return None
    kind: MediaKind = item.get("type") if item.get("type") in _KINDS else "photo"
    file_id = item.get("file_id")
    if file_id:
        return MediaEntry(kind=kind, file_id=str(file_id))
    media_id = item.get("media_id")
    if isinstance(media_id, int) and not isinstance(media_id, bool):
        return MediaEntry(kind=kind, media_id=media_id)
    return None


async def _resolve_media(entry: MediaEntry, media_client: Any) -> Any:
    """file_id как есть; media_id → байты из медиа-сервиса; None — пропустить."""
    if entry.file_id:
        return entry.file_id
    if media_client is None:
        logger.warning("media_id=%s пропущен: media-service выключен", entry.media_id)
        return None
    downloaded = await media_client.download_media_file(entry.media_id)
    if downloaded is None:
        return None
    data, content_type = downloaded
    ext = _EXT_BY_MIME.get((content_type or "").split(";")[0].strip(), "")
    return BufferedInputFile(data, filename=f"media_{entry.media_id}{ext}")


async def build_input_media(entries: Sequence[MediaEntry], media_client: Any) -> list[Any]:
    """Список InputMedia* для медиагруппы; нерезолвленные записи выпадают."""
    items: list[Any] = []
    for entry in entries:
        media = await _resolve_media(entry, media_client)
        if media is None:
            continue
        items.append(_INPUT_MEDIA_BY_KIND[entry.kind](media=media))
    return items


async def send_media_entries(
    message: Message,
    entries: Sequence[MediaEntry],
    media_client: Any,
    *,
    first_caption: Optional[str] = None,
) -> int:
    """Отправить все записи в чат сообщения; вернуть число отправленных."""
    items = await build_input_media(entries, media_client)
    if not items:
        return 0
    if first_caption:
        items[0].caption = first_caption
    for start in range(0, len(items), TELEGRAM_MEDIA_GROUP_MAX):
        chunk = items[start:start + TELEGRAM_MEDIA_GROUP_MAX]
        if len(chunk) == 1:
            await _send_single(message, chunk[0])
        else:
            await message.answer_media_group(media=chunk)
    return len(items)


async def _send_single(message: Message, item: Any) -> None:
    if isinstance(item, InputMediaPhoto):
        await message.answer_photo(photo=item.media, caption=item.caption)
    elif isinstance(item, InputMediaVideo):
        await message.answer_video(video=item.media, caption=item.caption)
    else:
        await message.answer_document(document=item.media, caption=item.caption)
