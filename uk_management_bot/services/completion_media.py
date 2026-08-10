"""Чтение фотоотчёта заявки: media-service — источник правды, legacy-поле — фолбэк.

Решение владельца (2026-08-10): фотоотчёт (категории completion_*) читается из
media-service, потому что дашборд и TWA грузят файлы туда через media-proxy и
legacy-поле `Request.completion_media` не трогают. media-service заливает файл в
Telegram-канал и хранит настоящий `telegram_file_id`, поэтому бот отправляет
такие файлы обычным `answer_photo(file_id)` без скачивания байтов.

Legacy-поле остаётся страховкой, а не вторым источником: старые заявки, залитые
до media-service, и записи executor-flow, сделанные при недоступном media-service
(там лежат сырые telegram file_id). Писателей поля этот модуль не трогает.
"""

import json
import logging
from typing import Any, List

from uk_management_bot.integrations import get_media_client

logger = logging.getLogger(__name__)

# Зеркалит FileCategories media-прокси (совместный whitelist SEC-021).
COMPLETION_CATEGORIES = frozenset(
    {"completion_photo", "completion_video", "completion_document"}
)


def legacy_completion_file_ids(raw: Any) -> List[str]:
    """Достаёт telegram file_id из legacy `Request.completion_media`.

    Поле исторически разнородно: JSON-строка или list; элементы — строки-file_id
    либо dict'ы `{"type", "file_id"}` (fallback executor-flow). Dict'ы формы
    media-service (`{"media_id", "file_url", ...}`) file_id не содержат и
    пропускаются — их содержимое и так придёт из media-service.
    """
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(raw, list):
        return []
    file_ids: List[str] = []
    for item in raw:
        if isinstance(item, str) and item:
            file_ids.append(item)
        elif isinstance(item, dict) and item.get("file_id"):
            file_ids.append(item["file_id"])
    return file_ids


async def get_completion_media_file_ids(request_number: str, legacy_raw: Any) -> List[str]:
    """Telegram file_id фотоотчёта заявки: media-service, при пустоте/сбое — legacy.

    Один вызов списка без фильтра категории (фильтруем сами): категорий три,
    а поход по HTTP один.
    """
    client = get_media_client()
    if client is not None:
        try:
            # retries=1: у нас мгновенный фолбэк на legacy-поле, бэкофф-ожидание
            # ретраев (~1.5 c) в интерактивном хендлере хуже быстрого фолбэка.
            items = await client.get_request_media(request_number, retries=1) or []
            file_ids = [
                item["telegram_file_id"]
                for item in items
                if isinstance(item, dict)
                and item.get("category") in COMPLETION_CATEGORIES
                and item.get("telegram_file_id")
            ]
            if file_ids:
                return file_ids
        except Exception as e:  # noqa: BLE001 — недоступность сервиса не должна ронять хендлер
            logger.warning(
                "media-service недоступен для фотоотчёта %s, используем legacy-поле: %s",
                request_number,
                e,
            )
    return legacy_completion_file_ids(legacy_raw)
