"""Менеджерский REST API визуальных отчётов «до/после» (/api/v2/work-reports, T7).

Роутер тонкий: вся доменная логика — в `services/work_report_service.py`
(T5/T6). Здесь — HTTP-обвязка: маппинг `WorkReportPublishError`/
`MediaValidationError` на HTTPException, коммит после вызовов, которые сами
не коммитят (`autofill_media`), и НЕ коммитим повторно после вызовов,
которые уже коммитят внутри себя (`sync_pending_drafts`,
`revoke_stale_publications`, вся сага публикации).

Фиче-флаг `settings.WORK_REPORTS_ENABLED` гейтит ВЕСЬ роутер единым 404 (не
403/иной код) — не палит наличие фичи неавторизованному/не-менеджеру.

ВСЕ статичные пути объявлены до динамического `/{report_id}`-блока (house
style, см. `api/materials/router.py:11,311`). Сегодня коллизий не было бы и
при обратном порядке (у `/settings`/`/reconcile` нет одноимённых динамических
соседей с тем же методом), но добавление `PUT`/`POST /{report_id}` тихо
перехватило бы их — порядок держим строгим, чтобы этот класс поломки был
невозможен, а не «маловероятен».
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.board_config.schemas import WorkReportsCfg
from uk_management_bot.api.board_config.service import load_board_config, merge_and_save_board_config
from uk_management_bot.api.dependencies import get_db, require_approved_roles
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.api.work_reports import coordination
from uk_management_bot.api.work_reports import service as api_service
from uk_management_bot.api.work_reports.schemas import (
    WorkReportCreateIn,
    WorkReportListOut,
    WorkReportOut,
    WorkReportPatchIn,
    WorkReportRejectIn,
    WorkReportsSettingsIn,
    WorkReportUnpublishIn,
)
from uk_management_bot.config.settings import settings
from uk_management_bot.constants.work_reports import MEDIA_EDITABLE_STATUSES
# Alias — `Request` (fastapi) нужен для slowapi rate-limit сигнатуры ниже
# (см. тот же приём в api/requests/router.py, api/public/router.py).
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.work_report import WorkReport
from uk_management_bot.integrations import get_media_client
from uk_management_bot.services import work_report_service
from uk_management_bot.services.request_address import format_building_address, format_yard_address
from uk_management_bot.services.work_report_service import (
    MediaValidationError,
    WorkReportPublishError,
    derive_public_address,
)
from uk_management_bot.utils.workflow_predicates import is_report_eligible

logger = logging.getLogger(__name__)


async def _require_work_reports_enabled() -> None:
    if not settings.WORK_REPORTS_ENABLED:
        raise HTTPException(status_code=404, detail="Not Found")


router = APIRouter(dependencies=[Depends(_require_work_reports_enabled)])
# `require_approved_roles`, а не `require_roles`: этот модуль публикует контент в
# открытый интернет, поэтому не-approved менеджер (pending/blocked-на-модерации)
# не должен им управлять. Строже, чем PUT /board-config (там `require_roles`), и
# совпадает с модулем материалов (`api/materials/router.py:53`).
_manager_only = require_approved_roles("manager")

# Статусы отчёта: канон — constants/work_reports.py (AUD6-P2-57). Literal
# обязан остаться литеральным (статическая типизация не собирается из
# кортежа) — его равенство канону держит гейт
# tests/api/test_work_report_status_ssot.py.
ReportStatus = Literal["pending", "needs_media", "publishing", "published", "needs_review", "rejected"]
_MEDIA_EDITABLE_STATUSES = MEDIA_EDITABLE_STATUSES

# Троттлинг автоматического reconcile внутри /sync — per-worker in-memory,
# намеренно неточно между воркерами (см. план); ручной POST /reconcile этот
# троттл не использует.
_last_reconcile_at: Optional[datetime] = None
_RECONCILE_THROTTLE = timedelta(minutes=5)


def _publish_error_to_http(exc: WorkReportPublishError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


async def _resolve_manual_address(
    db: AsyncSession,
    request_row: RequestModel,
    building_id: Optional[int],
    yard_id: Optional[int],
) -> str:
    """Единая логика адреса для ручного create/PATCH — используется и
    `POST ""`, и `PATCH "/{report_id}"` (см. комментарий в описании задачи:
    дублировать ~20 строк ветвления хуже, чем один общий хелпер).

    Legacy-заявка (address_type не apartment/building/yard): требует РОВНО
    один из building_id/yard_id, ищет сущность, форматирует каноническим
    форматтером. Структурированная заявка: попытка override (любой из id
    передан) — 422 `address_override_not_allowed`; иначе адрес выводится из
    самой заявки через `derive_public_address` (с eager-load цепочки, как в
    `work_report_service.sync_pending_drafts`).
    """
    is_legacy = request_row.address_type not in ("apartment", "building", "yard")

    if is_legacy:
        if (building_id is None) == (yard_id is None):
            raise HTTPException(
                status_code=422,
                detail="legacy request requires exactly one of building_id/yard_id",
            )
        if building_id is not None:
            building = await api_service.building_with_yard(db, building_id)
            if building is None:
                raise HTTPException(status_code=422, detail=f"building {building_id} not found")
            return format_building_address(building)

        yard = await api_service.yard_by_id(db, yard_id)
        if yard is None:
            raise HTTPException(status_code=422, detail=f"yard {yard_id} not found")
        return format_yard_address(yard)

    if building_id is not None or yard_id is not None:
        raise HTTPException(status_code=422, detail="address_override_not_allowed")

    loaded = await api_service.request_with_address_chain(db, request_row.request_number)
    address = derive_public_address(loaded)
    if address is None:
        raise HTTPException(status_code=422, detail="could not derive public address")
    return address


# ── GET / list ───────────────────────────────────────────────────────────


@router.get("", response_model=WorkReportListOut)
async def list_work_reports(
    # Literal, а не свободная строка: опечатка в фильтре должна давать 422, а не
    # тихо пустой список, который читается как «отчётов нет».
    # AUD6-P2-08: параметр повторяемый (?status=a&status=b) — очередь модерации
    # объединяет pending/needs_media/publishing одним запросом; одиночное
    # значение работает как раньше.
    status: Optional[list[ReportStatus]] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
) -> WorkReportListOut:
    rows, total = await api_service.work_reports_page(
        db, statuses=list(status) if status else None, limit=limit, offset=offset
    )
    return WorkReportListOut(items=list(rows), total=total, limit=limit, offset=offset)


# ── POST /sync ───────────────────────────────────────────────────────────


@router.post("/sync")
@limiter.limit("30/minute")
async def sync_work_reports(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
) -> dict:
    """Автосинк черновиков + автопубликация (если включена) + отзыв устаревших
    публикаций + (троттлено раз в 5 минут на воркер) сверка publication-lock'ов.

    `user.id` уходит в автопубликацию как `triggered_by` — это «кто включил
    режим», НЕ «кто одобрил контент»; в аудите оно и лежит отдельным ключом
    (см. `publish_report(automatic=True)`)."""
    global _last_reconcile_at

    sync_result = await work_report_service.sync_pending_drafts(db)

    media_client = get_media_client()
    autopublish_result = None
    if media_client is not None:
        autopublish_result = await work_report_service.autopublish_ready_drafts(
            db, media_client, triggered_by=user.id
        )

    revoked = await work_report_service.revoke_stale_publications(db)

    reconcile_result = None
    reconcile_error = None
    now = datetime.now(timezone.utc)
    # AUD6-P2-05: троттл межворкерный (Redis SET NX EX) — при --workers 2
    # процессный давал ДВА reconcile за окно, расширяя гонку AUD6-P2-04.
    # Redis недоступен (None) → прежний процессный троттл как деградация.
    #
    # Порядок важен: слот берётся ТОЛЬКО когда сверка вообще возможна. Пока он
    # брался раньше проверки media-клиента, /sync без клиента (media не
    # сконфигурирован либо клиент ещё не поднялся) съедал пятиминутное окно, не
    # сверив ничего, — и при --workers 2 отбирал его у воркера, который сверку
    # сделать мог, то есть частично возвращал ту самую гонку AUD6-P2-04.
    should_reconcile = False
    if media_client is not None:
        slot = await coordination.try_acquire_reconcile_slot(
            int(_RECONCILE_THROTTLE.total_seconds())
        )
        should_reconcile = slot if slot is not None else (
            _last_reconcile_at is None or now - _last_reconcile_at >= _RECONCILE_THROTTLE
        )
    if should_reconcile:
        # Сверка — фоновая maintenance-операция, ехавшая прицепом к /sync, и она
        # НЕ должна ронять ответ: синк, автопубликация и отзыв выше уже
        # закоммичены, а `list_publication_locks` намеренно бросает при ошибке
        # media-service (глотать её внутри reconcile нельзя — по пустой
        # инвентаризации он снял бы живые локи). Поэтому изолируем здесь:
        # иначе лежащий media-service делал бы 500 на единственном входе
        # менеджера в очередь при полностью успешной полезной работе.
        try:
            reconcile_result = await work_report_service.reconcile_publication_locks(
                db, media_client
            )
        except Exception as e:
            # Сессия могла остаться в failed-транзакции (reconcile коммитит
            # внутри себя, но упасть может и посередине) — откатываем, чтобы
            # не отдать 500 уже на сериализации ответа.
            await db.rollback()
            reconcile_error = type(e).__name__
            logger.warning("reconcile_publication_locks не прошёл внутри /sync: %s", e)
        finally:
            # Стамп в finally, а не после успеха: иначе при недоступном
            # media-service троттл не включается, и каждый следующий /sync
            # снова упирается в тот же таймаут.
            _last_reconcile_at = now

    return {
        "sync": sync_result,
        "autopublish": autopublish_result,
        "revoked": revoked,
        "reconcile": reconcile_result,
        # Явное поле, а не молчание: оператор должен видеть, что сверка локов
        # не выполнилась, даже когда всё остальное прошло.
        "reconcile_error": reconcile_error,
    }


# ── POST / create ────────────────────────────────────────────────────────


@router.post("", response_model=WorkReportOut, status_code=201)
async def create_work_report(
    body: WorkReportCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
) -> WorkReport:
    existing = await api_service.report_by_request_number(db, body.request_number)
    if existing is not None:
        raise HTTPException(
            status_code=409, detail=f"work report for {body.request_number} already exists"
        )

    request_row = await api_service.request_by_number(db, body.request_number)
    if request_row is None:
        raise HTTPException(status_code=404, detail=f"request {body.request_number} not found")
    if not is_report_eligible(request_row):
        raise HTTPException(
            status_code=409, detail=f"request {body.request_number} is not report-eligible"
        )

    address = await _resolve_manual_address(db, request_row, body.building_id, body.yard_id)

    # Ленивый импорт — keyboards.requests тянет aiogram.types (тот же приём,
    # что и в work_report_service.sync_pending_drafts).
    from uk_management_bot.keyboards.requests import resolve_category_key

    performed_at = request_row.completed_at or request_row.updated_at or request_row.created_at
    report = WorkReport(
        request_number=request_row.request_number,
        category_key=resolve_category_key(request_row.category),
        address_public=address,
        performed_at=performed_at,
        before_media_ids=[],
        after_media_ids=[],
        media_meta=[],
        locked_media_ids=[],
        status="pending",
        source="manual",
    )
    return await api_service.persist_manual_report(db, report)


# ── POST /autofill-pending ───────────────────────────────────────────────


@router.post("/autofill-pending")
async def autofill_pending(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
) -> dict:
    media_client = get_media_client()
    if media_client is None:
        raise HTTPException(status_code=503, detail="media service not configured")

    # AUD6-P1-3: раньше здесь брался `with_for_update()` сразу на 20 строк, и
    # транзакция с локами держалась через до 40 сетевых вызовов в media-service
    # (таймаут 30 с × 3 ретрая каждый) — параллельный /sync блокировался на тех
    # же строках на минуты. Теперь: кандидаты выбираются БЕЗ лока, сеть идёт до
    # лока (fetch_media_selection), запись — короткой per-report транзакцией с
    # перепроверкой статуса под локом. Защита от гонки с сагой публикации
    # сохранена той же перепроверкой: publishing в _MEDIA_EDITABLE_STATUSES не
    # входит, уехавшая строка молча пропускается (см. patch_work_report).
    candidates = await api_service.autofill_candidates(db, limit=20)
    processed = 0
    for report_id, request_number in candidates:
        try:
            before_ids, after_ids = await work_report_service.fetch_media_selection(
                media_client, request_number
            )
        except Exception as e:
            # Один сбойный запрос не должен ронять весь батч 500-кой.
            logger.warning(
                "autofill-pending: отчёт %s не автозаполнен: %s", report_id, e
            )
            continue
        applied = await api_service.apply_autofill_locked(db, report_id, before_ids, after_ids)
        if applied:
            processed += 1
    return {"processed": processed}


# ── PUT /settings ─────────────────────────────────────────────────────────


@router.put("/settings", response_model=WorkReportsCfg)
async def update_work_reports_settings(
    body: WorkReportsSettingsIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
) -> WorkReportsCfg:
    """Обновить `work_reports`-блок board_config. Переиспользует
    `merge_and_save_board_config` — он же обслуживает PUT редактора витрины
    (см. его docstring) — а не переизобретает autopost_since-стамп здесь.

    `WorkReportsSettingsIn` не имеет поля `autopost_since` вообще — самый
    простой guard от смуглинга клиентского значения; сервис-слой всё равно
    бы его перезаписал (см. `merge_and_save_board_config`).
    """
    cfg = await load_board_config(db)
    merged = cfg.work_reports.model_dump()
    merged.update(body.model_dump(exclude_unset=True))

    result = await merge_and_save_board_config(db, {"work_reports": merged}, user.id)
    logger.info("work_reports settings обновлены пользователем %s", user.id)
    return result.work_reports


# ── POST /reconcile (ручной/операторский триггер, без троттла) ──────────


@router.post("/reconcile")
async def reconcile_work_reports(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
) -> dict:
    media_client = get_media_client()
    if media_client is None:
        raise HTTPException(status_code=503, detail="media service not configured")
    return await work_report_service.reconcile_publication_locks(db, media_client)


# ── POST /{report_id}/autofill ───────────────────────────────────────────


@router.post("/{report_id}/autofill", response_model=WorkReportOut)
async def autofill_one(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
) -> WorkReport:
    media_client = get_media_client()
    if media_client is None:
        raise HTTPException(status_code=503, detail="media service not configured")

    # `with_for_update()` (внутри locked_report): см. patch_work_report — без
    # блокировки строки это состязается с сагой публикации и может перезаписать
    # уже замороженный состав.
    report = await api_service.locked_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"work report {report_id} not found")
    if report.status not in _MEDIA_EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"work report {report_id} is {report.status}, expected pending or needs_media",
        )

    await work_report_service.autofill_media(db, media_client, report)
    await api_service.finalize_report(db, report)
    return report


# ── PATCH /{report_id} ───────────────────────────────────────────────────


@router.patch("/{report_id}", response_model=WorkReportOut)
async def patch_work_report(
    report_id: int,
    body: WorkReportPatchIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
) -> WorkReport:
    # `with_for_update()` ОБЯЗАТЕЛЕН, а не оптимизация. Без него проверка статуса
    # ниже — TOCTOU против саги публикации: её окно включает сетевой вызов в
    # media-service, и параллельный publish успевал полностью пройти между этим
    # SELECT'ом и коммитом ниже. Итог был: у опубликованного отчёта менялся
    # before/after-список, из-за чего наружу отдавался media_id БЕЗ
    # publication-lock и без записи в media_meta (Content-Type сваливался в
    # octet-stream), а вытесненный id оставался залоченным навсегда — reconcile
    # не видел его как осиротевший, потому что locked_media_ids всё ещё его
    # перечислял. Блокировка строки закрывает все точки склейки: любое
    # чередование оставляет статус publishing/published, и проверка ниже даёт 409.
    report = await api_service.locked_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"work report {report_id} not found")
    if report.status not in _MEDIA_EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"work report {report_id} is {report.status}, expected pending or needs_media",
        )

    fields = body.model_dump(exclude_unset=True)

    if "building_id" in fields or "yard_id" in fields:
        request_row = await api_service.request_by_number(db, report.request_number)
        if request_row is None:
            raise HTTPException(
                status_code=404, detail=f"request {report.request_number} not found"
            )
        report.address_public = await _resolve_manual_address(
            db, request_row, fields.get("building_id"), fields.get("yard_id")
        )

    if "category_key" in fields:
        report.category_key = fields["category_key"]

    if "before_media_ids" in fields or "after_media_ids" in fields:
        media_client = get_media_client()
        if media_client is None:
            raise HTTPException(status_code=503, detail="media service not configured")

        new_before = fields.get("before_media_ids", report.before_media_ids)
        new_after = fields.get("after_media_ids", report.after_media_ids)
        try:
            await work_report_service.validate_media_ids(
                media_client, report.request_number, new_before, new_after
            )
        except MediaValidationError as e:
            raise HTTPException(status_code=422, detail=str(e))

        report.before_media_ids = new_before
        report.after_media_ids = new_after
        report.media_synced_at = datetime.now(timezone.utc)

        # Тот же переключатель pending<->needs_media, что и в autofill_media
        # — не расходиться с ним.
        both_sides_present = bool(new_before) and bool(new_after)
        if not both_sides_present and report.status == "pending":
            report.status = "needs_media"
        elif both_sides_present and report.status == "needs_media":
            report.status = "pending"

    await api_service.finalize_report(db, report)
    return report


# ── Publication saga endpoints ───────────────────────────────────────────


@router.post("/{report_id}/publish", response_model=WorkReportOut)
async def publish_work_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
) -> WorkReport:
    media_client = get_media_client()
    if media_client is None:
        raise HTTPException(status_code=503, detail="media service not configured")
    try:
        return await work_report_service.publish_report(db, media_client, report_id, user.id)
    except WorkReportPublishError as e:
        raise _publish_error_to_http(e)


@router.post("/{report_id}/unpublish", response_model=WorkReportOut)
async def unpublish_work_report(
    report_id: int,
    body: WorkReportUnpublishIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
) -> WorkReport:
    media_client = get_media_client()
    if media_client is None:
        raise HTTPException(status_code=503, detail="media service not configured")
    try:
        report = await work_report_service.unpublish_report(
            db, media_client, report_id, user.id, reason=body.reason
        )
    except WorkReportPublishError as e:
        raise _publish_error_to_http(e)
    # AUD6-P2-05: отзыв обязан пропасть из ПУБЛИЧНОЙ ленты всех воркеров сразу,
    # а не только того, где сработал (кэш соседей жил бы ещё до 30с TTL).
    await coordination.bump_cache_epoch()
    return report


@router.post("/{report_id}/reject", response_model=WorkReportOut)
async def reject_work_report(
    report_id: int,
    body: WorkReportRejectIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
) -> WorkReport:
    try:
        report = await work_report_service.reject_report(db, report_id, user.id, body.reason)
    except WorkReportPublishError as e:
        raise _publish_error_to_http(e)
    # Reject опубликованного — та же публичная видимость, что и unpublish.
    await coordination.bump_cache_epoch()
    return report


@router.post("/{report_id}/reopen", response_model=WorkReportOut)
async def reopen_work_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
) -> WorkReport:
    try:
        return await work_report_service.reopen_report(db, report_id, user.id)
    except WorkReportPublishError as e:
        raise _publish_error_to_http(e)
