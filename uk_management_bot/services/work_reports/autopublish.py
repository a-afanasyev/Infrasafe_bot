"""Режим «без модерации»: `autopublish_ready_drafts` — дозаполнить черновики
медиа и опубликовать готовые через ту же сагу `publish_report`."""

import logging
import time
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.board_config.service import load_board_config
from uk_management_bot.database.models.work_report import WorkReport

logger = logging.getLogger(__name__)

_AUTOPUBLISH_BATCH_LIMIT = 20
# AUD6-P1-3: потолок времени на пакет автопубликации. При деградировавшем
# media-service каждый отчёт может стоить до ~90 с сетевых таймаутов — без
# потолка пакет из 20 растягивался на десятки минут внутри /sync и тика.
_AUTOPUBLISH_TIME_BUDGET_SECONDS = 60.0


def _svc():
    """Ленивое обращение к фасаду `services.work_report_service`: тесты и
    колл-сайты патчат атрибуты по имени фасада (включая
    `_AUTOPUBLISH_BATCH_LIMIT`), поэтому межмодульные вызовы и патчабельные
    константы внутри пакета читаются через него (см. докстринг пакета)."""
    from uk_management_bot.services import work_report_service

    return work_report_service


async def autopublish_ready_drafts(
    db: AsyncSession, media_client: Any, triggered_by: Optional[int] = None
) -> dict:
    """Режим «без модерации»: дозаполнить черновики медиа и опубликовать те, у
    которых нашлись обе стороны фото.

    Живёт отдельно от `sync_pending_drafts` (которая SQL-only и media-service не
    видит) — здесь нужен media_client. Вызывается из `POST /work-reports/sync`
    сразу после синка, поэтому «автопубликация» наступает при открытии очереди
    менеджером, а не в отдельном фоновом процессе.

    Что режим НЕ меняет:

    * список проверок в `publish_report` — eligibility заявки, безопасность
      адреса, наличие обеих сторон, перевалидация каждого media_id, взятие
      publication-lock. Ослаблена только человеческая проверка содержимого фото.

    Фильтр категорий (`cfg.work_reports.categories`) применяется ТОЛЬКО здесь —
    это единственное место, где он вообще есть. `sync_pending_drafts` его не
    применяет намеренно: очередь модерации наполняется по всем подходящим
    заявкам, иначе отфильтрованная заявка теряется безвозвратно (уезжает из
    14-дневного окна и не возвращается после снятия галочки). Отчёты вне
    списка остаются на модерации — их публикация всё ещё возможна руками, это
    сознательно: список ограничивает автоматику, а не запрещает менеджеру
    опубликовать конкретный отчёт осознанно.

    Черновик без одной из сторон остаётся `needs_media` (autofill сам его туда
    переводит) и в ленту не уезжает — то есть «без модерации» не означает
    «опубликовать что угодно». Ошибка публикации одного отчёта не срывает
    остальные: пакет продолжается, счётчик `failed` растёт.
    """
    cfg = await load_board_config(db)
    if not cfg.work_reports.autopublish:
        return {
            "published": 0,
            "left_for_moderation": 0,
            "skipped_by_category": 0,
            "failed": 0,
            "enabled": False,
        }

    pending_clause = WorkReport.status.in_(("pending", "needs_media"))
    allowed_categories = cfg.work_reports.categories
    # Фильтруем в SQL, а не в Python после выборки: иначе черновики чужих
    # категорий накапливались бы и съедали окно пакета (_AUTOPUBLISH_BATCH_LIMIT),
    # оставляя подходящие вечно неопубликованными.
    #
    # В SQL это безопасно (в отличие от sync_pending_drafts, где фильтр обязан
    # быть в Python): `WorkReport.category_key` — снапшот, в него всегда пишется
    # канон-ключ (`resolve_category_key`), легаси-RU-подписей там не бывает.
    category_clause = (
        WorkReport.category_key.in_(allowed_categories) if allowed_categories else None
    )

    # AUD6-P1-3: БЕЗ with_for_update — раньше пакет держал FOR UPDATE сразу на
    # 20 строках через все сетевые вызовы автозаполнения (до минут при
    # недоступном media), блокируя параллельный /sync менеджера на тех же
    # строках. Теперь сеть идёт до лока, а запись — короткой per-report
    # транзакцией с перепроверкой статуса (строка могла уехать, пока ходили
    # в сеть).
    stmt = select(WorkReport).where(pending_clause)
    if category_clause is not None:
        stmt = stmt.where(category_clause)
    candidates = (
        (await db.execute(
            stmt.order_by(WorkReport.created_at)
            .limit(_svc()._AUTOPUBLISH_BATCH_LIMIT)
        )).scalars().all()
    )

    # Отдельный счётчик, а не «доливка» в left_for_moderation: причины разные
    # (нет фото vs категория вне списка), и сводка в /sync должна их различать.
    skipped_by_category = 0
    if category_clause is not None:
        skipped_by_category = (
            await db.execute(
                select(func.count()).select_from(WorkReport)
                .where(pending_clause, ~category_clause)
            )
        ).scalar_one()

    # AUD6-P1-3: общий бюджет времени пакета. При деградировавшем media каждый
    # отчёт может стоить до ~90 с сетевых таймаутов — без потолка пакет из 20
    # растягивался на десятки минут; частичный результат честнее зависшего
    # /sync (недоделанные отчёты подберёт следующий тик/синк).
    deadline = time.monotonic() + _svc()._AUTOPUBLISH_TIME_BUDGET_SECONDS

    ready_ids: list[int] = []
    left = 0
    failed = 0
    for report in candidates:
        if time.monotonic() > deadline:
            logger.warning(
                "autopublish: бюджет времени пакета исчерпан на автозаполнении — "
                "обработано %d из %d кандидатов",
                len(ready_ids) + left + failed, len(candidates),
            )
            break
        # fetch ходит в media-service, а его клиент бросает на любой не-2xx
        # (`raise_for_status`) и на транспортных сбоях. Без этого перехвата
        # один сбойный запрос ронял весь POST /sync пятисоткой — вместе с
        # синком и ревокацией, которые к media-service отношения не имеют.
        try:
            before_ids, after_ids = await _svc().fetch_media_selection(
                media_client, report.request_number
            )
        except Exception as e:
            failed += 1
            logger.warning(
                "autopublish: автозаполнение отчёта %s не удалось: %s", report.id, e
            )
            continue
        # Короткая пишущая транзакция: лок + перепроверка статуса + запись.
        # Пока ходили в сеть, строку мог забрать publish/PATCH — перепроверяем
        # pending_clause под локом и молча пропускаем уехавшие.
        row = (
            await db.execute(
                select(WorkReport)
                .where(WorkReport.id == report.id, pending_clause)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            await db.commit()  # снять пустую транзакцию от select
            continue
        _svc().apply_media_selection(row, before_ids, after_ids)
        # Тот же критерий готовности, что в publish_report: нужен результат,
        # «до» опционально.
        ready = bool(row.after_media_ids)
        await db.commit()
        if ready:
            ready_ids.append(report.id)
        else:
            left += 1

    published = 0
    for report_id in ready_ids:
        if time.monotonic() > deadline:
            logger.warning(
                "autopublish: бюджет времени пакета исчерпан на публикации — "
                "опубликовано %d из %d готовых", published, len(ready_ids),
            )
            break
        # Широкий except по той же причине, что и у fetch выше: publish_report
        # берёт publication-lock через media-service, и его недоступность не
        # должна срывать остальной пакет и весь /sync.
        try:
            await _svc().publish_report(db, media_client, report_id, triggered_by, automatic=True)
            published += 1
        except Exception as e:
            failed += 1
            logger.warning("autopublish: отчёт %s не опубликован: %s", report_id, e)

    if published or failed or skipped_by_category:
        logger.info(
            "autopublish: опубликовано %d, оставлено на модерации %d, "
            "пропущено по категории %d, ошибок %d",
            published, left, skipped_by_category, failed,
        )
    return {
        "published": published,
        "left_for_moderation": left,
        "skipped_by_category": skipped_by_category,
        "failed": failed,
        "enabled": True,
    }
