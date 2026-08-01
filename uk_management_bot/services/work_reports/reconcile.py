"""Фоновая сверка publication-lock'ов между БД бота и media-service —
self-healing саги публикации (`reconcile_publication_locks`)."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.work_report import WorkReport

logger = logging.getLogger(__name__)

_RECONCILE_STALE_MINUTES = 15


def _svc():
    """Ленивое обращение к фасаду `services.work_report_service`: тесты и
    колл-сайты патчат атрибуты по имени фасада, поэтому межмодульные вызовы
    внутри пакета идут через него (см. докстринг пакета)."""
    from uk_management_bot.services import work_report_service

    return work_report_service


async def reconcile_publication_locks(db: AsyncSession, media_client: Any) -> dict:
    """Три направления самолечения:

    1. Отчёт застрял в `publishing` дольше 15 минут (крэш между шагом 6 и
       шагом 9 publish_report) → снять все его locked_media_ids, вернуть
       `pending`.
    2. Locked id в инвентаризации media-service, не встречающийся ни в одном
       `published`/`publishing` отчёте здесь — осиротевший lock (крэш между
       успешным acquire в media-service и записью id в `locked_media_ids`,
       см. шаг 7 publish_report) → снять.
    3. Media id из отчёта-держателя lock'а (см. `_LOCK_HOLDING_STATUSES`),
       отсутствующий среди locked в media-service — самолечение после
       отдельного сбоя media-service → взять заново; неудача повторного
       acquire — best-effort (лог warning, не бросает исключение и не прерывает
       остальную сверку — это фоновая maintenance-функция, а не
       пользовательский запрос).

    4. Строки media-service, зависшие в транзиентных `archiving`/`deleting`
       (крэш посреди саги архивации/удаления), доводятся до терминального
       статуса. Делает это сам media-service — только он знает семантику своих
       переходов и видит строки независимо от наличия lock'а (`GET
       /publication-locks` показывает лишь `publication_locked=true`). Здесь —
       только вызов; направления и их обоснование в
       `MediaStorageService.resolve_stale_transitions`.
    """
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(minutes=_RECONCILE_STALE_MINUTES)

    # 1) Отчёты, застрявшие в `publishing` дольше _RECONCILE_STALE_MINUTES —
    # снять их locks и вернуть в pending.
    stale_reports = (await db.execute(
        select(WorkReport).where(
            WorkReport.status == "publishing",
            WorkReport.state_changed_at < stale_before,
        ).with_for_update()
    )).scalars().all()
    unstuck = 0
    for report in stale_reports:
        for media_id in report.locked_media_ids:
            await media_client.release_publication_lock(media_id)
        report.locked_media_ids = []
        report.status = "pending"
        report.state_changed_at = now
        unstuck += 1
    if stale_reports:
        # Один commit на весь батч — не по-репорту, в отличие от
        # publish_report. Безопасно: release_publication_lock идемпотентен,
        # так что крэш посреди батча означает лишь, что следующий прогон
        # reconcile повторно отпустит уже отпущенные id как no-op. У
        # publish_report'а per-lock commit важен по другой причине — там
        # acquire НЕ идемпотентен в этом же смысле (лок либо взят, либо нет),
        # и locked_media_ids обязан отражать реальность на случай крэша.
        await db.commit()

    # 2) Инвентаризация media-service — источник истины "что реально
    # залочено". Locked id, не встречающийся ни в одном published/publishing
    # отчёте здесь — осиротевший lock, снять.
    inventory_ids: set[int] = set()
    offset = 0
    while True:
        page = await media_client.list_publication_locks(limit=200, offset=offset)
        items = page.get("items", [])
        inventory_ids.update(item["id"] for item in items)
        if len(items) < 200:
            break
        offset += 200

    covered_ids: set[int] = set()
    live_rows = (await db.execute(
        select(WorkReport.locked_media_ids).where(WorkReport.status.in_(_svc()._LOCK_HOLDING_STATUSES))
    )).all()
    for (ids,) in live_rows:
        covered_ids.update(ids or [])

    orphaned = inventory_ids - covered_ids
    orphan_release_deferred = 0
    if orphaned:
        # AUD6-P2-04: TOCTOU между двумя БД. Сага publish уже получила lock в
        # media-service (шаг 6), но locked_media_ids ещё не закоммичен — в этом
        # окне id выглядит осиротевшим, и снятие оставило бы публикацию с
        # незалоченным медиа (файл может быть заархивирован из-под неё). Пока
        # есть отчёты в `publishing` — снятие орфанов пропускаем целиком:
        # настоящий орфан никому не мешает до следующего тихого прогона, а
        # ДОЛГО зависшие publishing уже возвращены в pending пунктом 1 выше
        # (порядок пунктов — часть корректности этого пропуска).
        in_flight = (await db.execute(
            select(func.count()).select_from(WorkReport)
            .where(WorkReport.status == "publishing")
        )).scalar_one()
        if in_flight:
            logger.info(
                "reconcile: снятие %d орфан-локов отложено — %d отчётов в publishing",
                len(orphaned), in_flight,
            )
            orphan_release_deferred = len(orphaned)
            orphaned = set()
    for media_id in orphaned:
        await media_client.release_publication_lock(media_id)

    # 3) Обратное направление: media id из published/publishing отчёта,
    # отсутствующий среди locked в media-service — взять заново (best-effort).
    missing = covered_ids - inventory_ids
    relocked = 0
    for media_id in missing:
        ok = await media_client.acquire_publication_lock(media_id)
        if ok:
            relocked += 1
        else:
            logger.warning(
                "reconcile_publication_locks: could not re-acquire lock for media %d "
                "(likely archived without an active lock — see module docstring "
                "on the archiving/deleting recovery gap)", media_id,
            )

    # 4) Зависшие транзиентные статусы в media-service — его собственная
    # ответственность (см. docstring). Best-effort: клиент проглатывает сбой и
    # возвращает {}, чтобы недоступность media-service не обнулила пункты 1–3.
    stale_transitions = await media_client.resolve_stale_transitions(
        older_than_minutes=_RECONCILE_STALE_MINUTES
    )

    return {
        "unstuck_publishing": unstuck,
        "orphaned_locks_released": len(orphaned),
        "orphan_release_deferred": orphan_release_deferred,
        "missing_locks_relocked": relocked,
        "stale_transitions": stale_transitions,
    }
