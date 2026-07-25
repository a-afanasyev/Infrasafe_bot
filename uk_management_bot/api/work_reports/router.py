"""Менеджерский REST API визуальных отчётов «до/после» (/api/v2/work-reports, T7).

Роутер тонкий: вся доменная логика — в `services/work_report_service.py`
(T5/T6). Здесь — HTTP-обвязка: маппинг `WorkReportPublishError`/
`MediaValidationError` на HTTPException, коммит после вызовов, которые сами
не коммитят (`autofill_media`), и НЕ коммитим повторно после вызовов,
которые уже коммитят внутри себя (`sync_pending_drafts`,
`revoke_stale_publications`, вся сага публикации).

Фиче-флаг `settings.WORK_REPORTS_ENABLED` гейтит ВЕСЬ роутер единым 404 (не
403/иной код) — не палит наличие фичи неавторизованному/не-менеджеру.

Большинство статичных путей объявлено до `/{report_id}` (house style, см.
`api/materials/router.py`); `/settings` и `/reconcile` — исключение, идут
ПОСЛЕ динамического блока. Это не routing-опасность (разные HTTP-методы/
шейпы у всех путей ниже — коллизии в принципе нет), просто порядок в файле
не строго "все статичные сначала".
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from uk_management_bot.api.board_config.schemas import WorkReportsCfg
from uk_management_bot.api.board_config.service import load_board_config, merge_and_save_board_config
from uk_management_bot.api.dependencies import get_db, require_roles
from uk_management_bot.api.rate_limit import limiter
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
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
# Alias — `Request` (fastapi) нужен для slowapi rate-limit сигнатуры ниже
# (см. тот же приём в api/requests/router.py, api/public/router.py).
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.user import User
from uk_management_bot.database.models.work_report import WorkReport
from uk_management_bot.database.models.yard import Yard
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
_manager_only = require_roles("manager")

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
            building = (
                await db.execute(
                    select(Building)
                    .options(selectinload(Building.yard))
                    .where(Building.id == building_id)
                )
            ).scalar_one_or_none()
            if building is None:
                raise HTTPException(status_code=422, detail=f"building {building_id} not found")
            return format_building_address(building)

        yard = (await db.execute(select(Yard).where(Yard.id == yard_id))).scalar_one_or_none()
        if yard is None:
            raise HTTPException(status_code=422, detail=f"yard {yard_id} not found")
        return format_yard_address(yard)

    if building_id is not None or yard_id is not None:
        raise HTTPException(status_code=422, detail="address_override_not_allowed")

    loaded = (
        await db.execute(
            select(RequestModel)
            .options(
                selectinload(RequestModel.building_obj).selectinload(Building.yard),
                selectinload(RequestModel.apartment_obj)
                .selectinload(Apartment.building)
                .selectinload(Building.yard),
                selectinload(RequestModel.yard_obj),
            )
            .where(RequestModel.request_number == request_row.request_number)
        )
    ).scalar_one()
    address = derive_public_address(loaded)
    if address is None:
        raise HTTPException(status_code=422, detail="could not derive public address")
    return address


# ── GET / list ───────────────────────────────────────────────────────────


@router.get("", response_model=WorkReportListOut)
async def list_work_reports(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
) -> WorkReportListOut:
    filters = [WorkReport.status == status] if status is not None else []

    total = (
        await db.execute(select(func.count()).select_from(WorkReport).where(*filters))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                select(WorkReport)
                .where(*filters)
                .order_by(WorkReport.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
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
    """Автосинк черновиков + отзыв устаревших публикаций + (троттлено раз в
    5 минут на воркер) фоновая сверка publication-lock'ов."""
    global _last_reconcile_at

    sync_result = await work_report_service.sync_pending_drafts(db)
    revoked = await work_report_service.revoke_stale_publications(db)

    reconcile_result = None
    media_client = get_media_client()
    now = datetime.now(timezone.utc)
    if media_client is not None and (
        _last_reconcile_at is None or now - _last_reconcile_at >= _RECONCILE_THROTTLE
    ):
        reconcile_result = await work_report_service.reconcile_publication_locks(db, media_client)
        _last_reconcile_at = now

    return {"sync": sync_result, "revoked": revoked, "reconcile": reconcile_result}


# ── POST / create ────────────────────────────────────────────────────────


@router.post("", response_model=WorkReportOut, status_code=201)
async def create_work_report(
    body: WorkReportCreateIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
) -> WorkReport:
    existing = (
        await db.execute(
            select(WorkReport).where(WorkReport.request_number == body.request_number)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409, detail=f"work report for {body.request_number} already exists"
        )

    request_row = (
        await db.execute(
            select(RequestModel).where(RequestModel.request_number == body.request_number)
        )
    ).scalar_one_or_none()
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
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


# ── POST /autofill-pending ───────────────────────────────────────────────


@router.post("/autofill-pending")
async def autofill_pending(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
) -> dict:
    media_client = get_media_client()
    if media_client is None:
        raise HTTPException(status_code=503, detail="media service not configured")

    rows = (
        (
            await db.execute(
                select(WorkReport)
                .where(WorkReport.media_synced_at.is_(None))
                .order_by(WorkReport.created_at)
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    for report in rows:
        await work_report_service.autofill_media(db, media_client, report)
    await db.commit()
    return {"processed": len(rows)}


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

    report = (
        await db.execute(select(WorkReport).where(WorkReport.id == report_id))
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail=f"work report {report_id} not found")

    await work_report_service.autofill_media(db, media_client, report)
    await db.commit()
    await db.refresh(report)
    return report


# ── PATCH /{report_id} ───────────────────────────────────────────────────


@router.patch("/{report_id}", response_model=WorkReportOut)
async def patch_work_report(
    report_id: int,
    body: WorkReportPatchIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
) -> WorkReport:
    report = (
        await db.execute(select(WorkReport).where(WorkReport.id == report_id))
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail=f"work report {report_id} not found")
    if report.status not in ("pending", "needs_media"):
        raise HTTPException(
            status_code=409,
            detail=f"work report {report_id} is {report.status}, expected pending or needs_media",
        )

    fields = body.model_dump(exclude_unset=True)

    if "building_id" in fields or "yard_id" in fields:
        request_row = (
            await db.execute(
                select(RequestModel).where(RequestModel.request_number == report.request_number)
            )
        ).scalar_one_or_none()
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

    await db.commit()
    await db.refresh(report)
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
        return await work_report_service.unpublish_report(
            db, media_client, report_id, user.id, reason=body.reason
        )
    except WorkReportPublishError as e:
        raise _publish_error_to_http(e)


@router.post("/{report_id}/reject", response_model=WorkReportOut)
async def reject_work_report(
    report_id: int,
    body: WorkReportRejectIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
) -> WorkReport:
    try:
        return await work_report_service.reject_report(db, report_id, user.id, body.reason)
    except WorkReportPublishError as e:
        raise _publish_error_to_http(e)


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
