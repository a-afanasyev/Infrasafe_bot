"""Чистка операций загрузки: зависшие ``pending`` и файлы заменённых фото.

Трогает только то, что заведомо никому не нужно:

* ``pending`` с арендой старше часа — обработчик умер; операция закрывается
  отказом ``abandoned`` (операцию со свежей арендой не трогаем — она в работе);
* файлы заменённых фото (исход ``superseded`` или активированное, но уже не
  текущее) старше срока хранения. Текущие фото и доказательства остаются.

# ponytail: файлы-сироты в медиа-сервисе (загружен, а строка не дошла до done)
# здесь не ищутся — проигравший аренду удаляет свой файл сам, а перехват
# зависшей операции перезаливает. Нужен обход по номеру `cl-*`, если
# наблюдение покажет утечку.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, or_, select, update

from uk_management_bot.database.models.cleaning import CleaningPhoto
from uk_management_bot.services.cleaning import rules
from uk_management_bot.services.cleaning.uploads import MediaDelete, _media_delete
from uk_management_bot.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

STALE_PENDING = timedelta(hours=1)
# Операцию моложе суток не закрываем: после временного сбоя медиа аренда сброшена
# (uploads._release), а очередь телефона ещё повторяет — отказ «abandoned» потерял бы кадр.
PENDING_KEEP = timedelta(hours=24)
_BATCH = 200


async def run(session_factory, *, now: Optional[datetime] = None,
              media_delete: MediaDelete = _media_delete) -> dict[str, int]:
    now = now or utc_now()
    async with session_factory() as db:
        retention = timedelta(days=int((await rules.latest(db)).data["superseded_retention_days"]))
        abandoned = await db.execute(
            update(CleaningPhoto)
            .where(CleaningPhoto.state == "pending", CleaningPhoto.claimed_at < now - STALE_PENDING,
                   CleaningPhoto.received_at < now - PENDING_KEEP)
            .values(state="done", outcome="refused", refusal_code="abandoned")
        )
        replaced = (await db.execute(
            select(CleaningPhoto.id, CleaningPhoto.media_id).where(
                CleaningPhoto.media_id.is_not(None), CleaningPhoto.received_at < now - retention,
                or_(CleaningPhoto.outcome == "superseded",
                    and_(CleaningPhoto.outcome == "activated", CleaningPhoto.is_current.is_(False))),
            ).limit(_BATCH)
        )).all()
        await db.commit()

    dropped = 0
    for photo_id, media_id in replaced:
        await media_delete(media_id)  # не бросает; повторное удаление безвредно
        async with session_factory() as db:
            await db.execute(update(CleaningPhoto).where(CleaningPhoto.id == photo_id).values(media_id=None))
            await db.commit()
        dropped += 1
    return {"abandoned": abandoned.rowcount, "files_dropped": dropped}
