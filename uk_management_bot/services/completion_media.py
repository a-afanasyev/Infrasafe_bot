"""Чтение фотоотчёта заявки: media-service — источник правды, legacy-поле — фолбэк.

Решение владельца (2026-08-10): фотоотчёт (категории completion_*) читается из
media-service, потому что дашборд и TWA грузят файлы туда через media-proxy и
legacy-поле `Request.completion_media` не трогают.

Файлы media-service отдаются как `MediaEntry(media_id=…)` и уходят в Telegram
БАЙТАМИ (`services/request_media_entries.send_media_entries`): media-service
живёт под своим бот-токеном (`MEDIA_BOT_TOKEN`), его `telegram_file_id` для
основного бота не годится («wrong file identifier»).

Legacy-поле остаётся страховкой, а не вторым источником: старые заявки, залитые
до media-service, и записи executor-flow, сделанные при недоступном media-service
(там лежат сырые telegram file_id основного бота). Писателей поля этот модуль не
трогает.
"""

import logging
from typing import Any, List

from uk_management_bot.integrations import get_media_client
from uk_management_bot.services.request_media_entries import MediaEntry, parse_media_entries

logger = logging.getLogger(__name__)

# Зеркалит FileCategories media-прокси (совместный whitelist SEC-021).
COMPLETION_CATEGORIES = frozenset(
    {"completion_photo", "completion_video", "completion_document"}
)
_KIND_BY_CATEGORY = {
    "completion_photo": "photo",
    "completion_video": "video",
    "completion_document": "document",
}


def legacy_completion_entries(raw: Any) -> List[MediaEntry]:
    """Записи legacy `Request.completion_media` с telegram file_id основного бота.

    Поле исторически разнородно (см. `parse_media_entries`). Dict'ы формы
    media-service (`{"media_id", "file_url", ...}`) пропускаются — их содержимое
    и так приходит из media-service, а при его недоступности скачать их нельзя.
    """
    return [entry for entry in parse_media_entries(raw) if entry.file_id]


def _media_service_entry(item: Any) -> MediaEntry | None:
    if not isinstance(item, dict) or item.get("category") not in COMPLETION_CATEGORIES:
        return None
    media_id = item.get("id")
    if not isinstance(media_id, int) or isinstance(media_id, bool):
        return None
    kind = item.get("file_type")
    if kind not in ("photo", "video", "document"):
        kind = _KIND_BY_CATEGORY[item["category"]]
    return MediaEntry(kind=kind, media_id=media_id)


async def get_completion_media_entries(request_number: str, legacy_raw: Any) -> List[MediaEntry]:
    """Фотоотчёт заявки: media-service, при пустоте/сбое — legacy.

    Один вызов списка без фильтра категории (фильтруем сами): категорий три,
    а поход по HTTP один.
    """
    client = get_media_client()
    if client is not None:
        try:
            # retries=1: у нас мгновенный фолбэк на legacy-поле, бэкофф-ожидание
            # ретраев (~1.5 c) в интерактивном хендлере хуже быстрого фолбэка.
            items = await client.get_request_media(request_number, retries=1) or []
            entries = [e for e in map(_media_service_entry, items) if e is not None]
            if entries:
                return entries
        except Exception as e:  # noqa: BLE001 — недоступность сервиса не должна ронять хендлер
            logger.warning(
                "media-service недоступен для фотоотчёта %s, используем legacy-поле: %s",
                request_number,
                e,
            )
    return legacy_completion_entries(legacy_raw)
