"""Маркеры медиа-сервиса в `Request.media_files`: `{"media_id": int, "type": kind}`.

Единый формат для всех писателей: API (`api/routes/media_proxy.py`, загрузка
через дашборд/TWA) и бот (Group Intake — фото, пришедшее ГРУППОВОМУ боту,
A9-P2-5). Чтение и отправка в Telegram — `services/request_media_entries.py`
(байты из медиа-сервиса: чужой file_id основному боту не годится).

Модуль без aiogram — его импортирует и API.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional, Sequence

logger = logging.getLogger(__name__)


def extract_media_id(payload: object) -> Optional[int]:
    """`MediaUploadResponse` медиа-сервиса — конверт `{"media_file": {"id": …},
    "file_url", "message"}` (media_service/app/schemas/media.py), не плоский
    объект; плоский `id` принимается как запасная форма."""
    if not isinstance(payload, dict):
        return None
    nested = payload.get("media_file")
    candidate = nested.get("id") if isinstance(nested, dict) else payload.get("id")
    if isinstance(candidate, bool) or not isinstance(candidate, int):
        return None
    return candidate


def with_media_marker(current: Any, media_id: int, kind: str) -> Optional[list]:
    """Новый список колонки с маркером в конце; None — такой media_id уже есть.

    Исходное значение не мутируется (колонка — plain JSON без MutableList:
    вызывающий обязан ПЕРЕПРИСВОИТЬ результат, иначе строка не станет грязной).
    Legacy-формы: JSON-строка разбирается (битая → пустой список); не-список
    (строка file_id / dict) сохраняется элементом — `[*current]` разложил бы
    строку посимвольно и необратимо испортил колонку.
    """
    current = current or []
    if isinstance(current, str):
        try:
            current = json.loads(current) or []
        except (json.JSONDecodeError, TypeError):
            current = []
    if not isinstance(current, list):
        logger.warning("media_files не список (%s), оборачиваю", type(current).__name__)
        current = [current]
    if any(isinstance(m, dict) and m.get("media_id") == media_id for m in current):
        return None
    return [*current, {"media_id": media_id, "type": kind}]


def append_media_markers_sync(db: Any, request_number: str, media_ids: Sequence[int],
                              kind: str = "photo") -> None:
    """Sync-писатель маркеров (run_db-юнит бота); async-двойник —
    `api/routes/media_proxy._append_media_marker`.

    FOR UPDATE + populate_existing: параллельная загрузка в ту же заявку не
    затирает список, а строка из identity map не отдаёт устаревший
    media_files, прочитанный до лока (A9-P2-1).
    """
    from uk_management_bot.database.models.request import Request

    row = (
        db.query(Request)
        .filter(Request.request_number == request_number)
        .with_for_update()
        .populate_existing()
        .one_or_none()
    )
    if row is None:
        logger.warning("media markers %s: заявка не найдена, маркер не записан", request_number)
        return
    updated = row.media_files
    changed = False
    for media_id in media_ids:
        merged = with_media_marker(updated, media_id, kind)
        if merged is not None:
            updated, changed = merged, True
    if changed:
        row.media_files = updated
    db.commit()
