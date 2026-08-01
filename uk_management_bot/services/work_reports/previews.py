"""Прогрев превью медиа опубликованных отчётов: точечный (после publish)
и sweep последних опубликованных (страховка тика)."""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.work_report import WorkReport

logger = logging.getLogger(__name__)


async def warm_report_previews(media_client: Any, report: WorkReport) -> dict:
    """Построить превью для медиа отчёта заранее.

    Никогда не бросает: клиент media-service сам глотает ошибки (см.
    `MediaServiceClient.warm_previews`), а здесь ловим и всё остальное —
    прогрев обязан быть незаметным для вызывающего.
    """
    ids = list(report.before_media_ids) + list(report.after_media_ids)
    if not ids:
        return {}
    try:
        return await _warm_in_chunks(media_client, ids)
    except Exception as e:
        logger.warning(
            "Прогрев превью отчёта %s не удался: %s — превью построится по "
            "первому запросу", report.id, e,
        )
        return {}


# Сколько последних опубликованных отчётов подчищает тик. 24 — размер первой
# страницы публичного архива (`PAGE_SIZE` во фронте): ровно то, что житель
# видит, не открывая «Показать ещё».
_WARM_SWEEP_LIMIT = 24
# Прогрев одного id — это скачивание из Telegram (~1.5 с), а у клиента
# media-service таймаут 30 с. Пачку дробим, иначе 48 картинок в одном запросе
# гарантированно уходят в ReadTimeout (поймано на profk: прогрев не сработал
# вовсе). 8 ≈ 12 с — с запасом внутри таймаута.
_WARM_CHUNK = 8


async def _warm_in_chunks(media_client: Any, ids: list[int]) -> dict:
    """Прогреть список id пачками, сложив счётчики. Ошибка одной пачки не
    отменяет остальные: клиент возвращает пустой dict, мы просто идём дальше."""
    total: dict[str, int] = {"warmed": 0, "already_cached": 0, "failed": 0}
    for start in range(0, len(ids), _WARM_CHUNK):
        chunk = ids[start:start + _WARM_CHUNK]
        result = await media_client.warm_previews(chunk)
        for key in total:
            total[key] += int(result.get(key, 0) or 0)
        if not result:
            # Пустой ответ = сбой пачки (клиент глотает исключение). Считаем её
            # неуспешной целиком, чтобы сводка не выглядела как «всё хорошо».
            total["failed"] += len(chunk)
    return total


async def warm_recent_previews(
    db: AsyncSession, media_client: Any, limit: int = _WARM_SWEEP_LIMIT
) -> dict:
    """Догреть превью последних опубликованных отчётов.

    Страховка к прогреву в `publish_report`: покрывает отчёты, опубликованные
    когда media-service был недоступен, и кэш, вытесненный после рестарта тома
    или переполнения лимита заявок. Уже закэшированные id media-service
    пропускает по проверке существования файла, поэтому повторные прогоны почти
    бесплатны.
    """
    reports = (
        await db.execute(
            select(WorkReport)
            .where(WorkReport.status == "published")
            .order_by(WorkReport.published_at.desc(), WorkReport.id.desc())
            .limit(limit)
        )
    ).scalars().all()

    ids: list[int] = []
    for r in reports:
        ids.extend(list(r.before_media_ids) + list(r.after_media_ids))
    if not ids:
        return {}
    try:
        return await _warm_in_chunks(media_client, ids)
    except Exception as e:
        logger.warning("Догрев превью не удался: %s", e)
        return {}
