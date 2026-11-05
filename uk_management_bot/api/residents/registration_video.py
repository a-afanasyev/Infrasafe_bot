"""Кнопка «🎬 Видео о регистрации» в карточке жителя, бросившего регистрацию.

Ролик и подпись — те же, что бот шлёт на «Я житель» (``services/tutorial_videos``).
Отправка — напрямую в Bot API: сначала по file_id, который бот уже положил в
Redis (токен один → file_id один), иначе загрузка файла и запись file_id.

Одному жителю — не чаще раза в сутки (решение владельца 2026-11-05): штамп
``users.registration_video_sent_at`` ставит только успешная доставка.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from uk_management_bot.api import telegram_send
from uk_management_bot.database.models.user import User
from uk_management_bot.services import tutorial_videos
from uk_management_bot.utils.helpers import get_text

logger = logging.getLogger(__name__)

RESEND_AFTER = timedelta(days=1)


def sent_recently(user: User, now: Optional[datetime] = None) -> bool:
    sent_at = user.registration_video_sent_at
    if sent_at is None:
        return False
    if sent_at.tzinfo is None:  # sqlite отдаёт naive — в БД пишем UTC
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) - sent_at < RESEND_AFTER


async def _redis():
    try:
        return await tutorial_videos._get_redis()
    except Exception as exc:  # noqa: BLE001 — без кэша просто загрузим файл
        logger.warning("registration video: Redis недоступен: %s", type(exc).__name__)
        return None


async def send_registration_video(user: User) -> str:
    """Отправить ролик жителю. -> статус доставки (telegram_send.STATUS_*)."""
    lang = user.language or "ru"
    path = tutorial_videos.video_path("registration", lang)
    caption = get_text("tutorial.registration.caption", language=lang)
    try:
        key = tutorial_videos.file_id_cache_key(path)
    except OSError:
        logger.error("registration video: нет файла ролика %s", path.name)
        return telegram_send.STATUS_ERROR
    redis = await _redis()

    file_id = None
    if redis is not None:
        try:
            file_id = await redis.get(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("registration video: file_id не прочитан: %s", type(exc).__name__)
    if file_id:
        # mark_blocked=False: штамп пишет record_delivery_verdict в сессии запроса.
        result = await telegram_send.send_video(user.telegram_id, file_id, caption=caption, mark_blocked=False)
        # 400 не про чат — file_id не принят (протух) → загружаем файл заново.
        if result.ok or result.status != telegram_send.STATUS_ERROR or result.http_status != 400:
            return result.status

    result = await telegram_send.send_video(user.telegram_id, path, caption=caption, mark_blocked=False)
    new_id = ((result.result or {}).get("video") or {}).get("file_id") if result.ok else None
    if new_id and redis is not None:
        try:
            await redis.set(key, new_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("registration video: file_id не сохранён: %s", type(exc).__name__)
    return result.status
