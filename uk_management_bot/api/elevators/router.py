"""Роутер модуля «Лифты» (/api/v2/elevators, Ф3a).

Фиче-флаг ``settings.ELEVATORS_ENABLED`` гейтит ВЕСЬ роутер единым 404 (как
``api/work_reports/router.py``): выключенная фича не палит своё наличие ни
кодом 403, ни схемой. В OpenAPI-снапшот роуты попадают всегда.

RBAC только по роли (``require_approved_roles``):
* чтение реестра/карточки/журнала/графика/заявок, смена статуса, закрытие
  записи графика — executor | manager;
* паспорт, архив, график, конфиг, групповая приёмка — manager;
* ``/for-building/{id}`` — любая approved-роль; житель — только свои дома.

Роутер тонкий: транзакции — ``service.py``/``calendar_service.py``, доменная
логика — ``services/elevator_service``. Статичные пути и под-роутер графика
объявлены ДО динамического ``/{elevator_id}``.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import get_db, require_approved_roles
from uk_management_bot.api.elevators import service as api_service
from uk_management_bot.api.elevators.errors import http_error
from uk_management_bot.api.elevators.router_calendar import router as calendar_router
from uk_management_bot.api.elevators.schemas import (
    ElevatorArchiveIn,
    ElevatorBulkConfirmIn,
    ElevatorBulkConfirmItemOut,
    ElevatorCommissionIn,
    ElevatorCreateIn,
    ElevatorDetailOut,
    ElevatorEventOut,
    ElevatorListOut,
    ElevatorMiniOut,
    ElevatorPatchIn,
    ElevatorRequestRowOut,
    ElevatorStatus,
    ElevatorStatusChangeOut,
    ElevatorStatusIn,
    ElevatorSummaryOut,
    ElevatorsConfigIn,
    ElevatorsConfigOut,
    Lang,
    ElevatorSortField,
    RegistryFlag,
    SortOrder,
)
from uk_management_bot.api.elevators.presenters import build_bulk_item
from uk_management_bot.api.rate_limit import limiter
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.user import User
from uk_management_bot.services.elevator_service import ElevatorServiceError
from uk_management_bot.services.redis_pubsub import publish_request_event
from uk_management_bot.services.workflow_notifications import dispatch_notify_intents_detached
from uk_management_bot.utils.request_workflow import PrincipalRef, normalize_status


async def _require_elevators_enabled() -> None:
    if not settings.ELEVATORS_ENABLED:
        raise HTTPException(status_code=404, detail="Not Found")


router = APIRouter(dependencies=[Depends(_require_elevators_enabled)])

_staff = require_approved_roles("executor", "manager")
_manager_only = require_approved_roles("manager")
_any_approved = require_approved_roles("applicant", "executor", "inspector", "manager")


# ── Реестр (статичные пути) ──────────────────────────────────────────

@router.get("", response_model=ElevatorListOut)
async def list_elevators(
    yard_id: Optional[int] = Query(None),
    building_id: Optional[int] = Query(None),
    status: Optional[ElevatorStatus] = Query(None),
    flag: Optional[list[RegistryFlag]] = Query(None),
    include_archived: bool = Query(False),
    sort: Optional[ElevatorSortField] = Query(None),
    order: SortOrder = Query("asc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    lang: Lang = Query("ru"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_staff),
):
    query = api_service.RegistryQuery(
        yard_id=yard_id, building_id=building_id, status=status,
        flags=frozenset(flag or ()), include_archived=include_archived,
        sort=sort, order=order, limit=limit, offset=offset,
    )
    try:
        return await api_service.list_page(db, query, language=lang)
    except ElevatorServiceError as exc:
        raise http_error(exc)


@router.post("", response_model=ElevatorDetailOut, status_code=201)
async def create_elevator(
    body: ElevatorCreateIn,
    lang: Lang = Query("ru"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    try:
        return await api_service.create_tx(
            db, body.model_dump(exclude_unset=True), actor_user_id=user.id, language=lang
        )
    except ElevatorServiceError as exc:
        raise http_error(exc)


@router.get("/summary", response_model=ElevatorSummaryOut)
async def get_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_staff),
):
    return await api_service.summary(db)


@router.get("/config", response_model=ElevatorsConfigOut)
async def get_config(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    return await api_service.get_config(db)


@router.put("/config", response_model=ElevatorsConfigOut)
@limiter.limit("30/minute")
async def update_config(
    request: Request,
    body: ElevatorsConfigIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    """Патч конфига (строгий: неизвестный ключ → 422); ответ — реально сохранённый мёрж."""
    try:
        return await api_service.save_config_tx(
            db, body.model_dump(exclude_unset=True), actor_user_id=user.id
        )
    except ElevatorServiceError as exc:
        raise http_error(exc)


@router.get("/for-building/{building_id}", response_model=list[ElevatorMiniOut])
async def list_for_building(
    building_id: int,
    lang: Lang = Query("ru"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_any_approved),
):
    """Лифты дома для выбора в заявке; жителю — только дома с одобренной квартирой."""
    if not await api_service.can_view_building(db, user, building_id):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return await api_service.list_for_building(db, building_id, language=lang)


@router.post("/requests/bulk-confirm", response_model=list[ElevatorBulkConfirmItemOut])
@limiter.limit("10/minute")
async def bulk_confirm_requests(
    request: Request,
    body: ElevatorBulkConfirmIn,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    """Групповая приёмка (``MANAGER_CONFIRM``) с per-item результатом.

    Post-commit intents каждой удачной заявки диспетчатся так же, как при
    одиночном подтверждении в ``api/requests/router.py``: realtime — сразу,
    notify — в ``BackgroundTasks`` (автор заявки получает уведомление).
    """
    principal = PrincipalRef(kind="user", user_id=user.id, source="api")
    try:
        results = await api_service.bulk_confirm(body.request_numbers, principal=principal)
    except ElevatorServiceError as exc:
        raise http_error(exc)
    for item in results:
        if not item.ok or not item.post_commit_intents:
            continue
        old_status = normalize_status(item.old_state) if item.old_state is not None else None
        for intent in item.post_commit_intents:
            if intent.kind == "realtime":
                await publish_request_event("request.status_changed", {
                    "number": item.request_number,
                    "old_status": old_status,
                    "new_status": intent.data.get("status"),
                })
        background.add_task(
            dispatch_notify_intents_detached, item.request_number, item.post_commit_intents
        )
    return [build_bulk_item(item) for item in results]


# ── График (статичный /occurrences ДО /{elevator_id}) ────────────────

router.include_router(calendar_router)


# ── Карточка (динамические пути) ─────────────────────────────────────

@router.get("/{elevator_id}", response_model=ElevatorDetailOut)
async def get_elevator(
    elevator_id: int,
    lang: Lang = Query("ru"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_staff),
):
    try:
        return await api_service.get_detail(db, elevator_id, language=lang)
    except ElevatorServiceError as exc:
        raise http_error(exc)


@router.patch("/{elevator_id}", response_model=ElevatorDetailOut)
async def patch_elevator(
    elevator_id: int,
    body: ElevatorPatchIn,
    lang: Lang = Query("ru"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    patch = body.model_dump(exclude_unset=True)
    expected_version = patch.pop("expected_version", None)
    try:
        return await api_service.patch_tx(
            db, elevator_id, patch, actor_user_id=user.id,
            expected_version=expected_version, language=lang,
        )
    except ElevatorServiceError as exc:
        raise http_error(exc)


@router.post("/{elevator_id}/commission", response_model=ElevatorDetailOut)
async def commission_elevator(
    elevator_id: int,
    body: ElevatorCommissionIn,
    lang: Lang = Query("ru"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    try:
        return await api_service.commission_tx(
            db, elevator_id, actor_user_id=user.id,
            commissioned_at=body.commissioned_at, language=lang,
        )
    except ElevatorServiceError as exc:
        raise http_error(exc)


@router.post("/{elevator_id}/archive", response_model=ElevatorDetailOut)
async def archive_elevator(
    elevator_id: int,
    body: ElevatorArchiveIn,
    lang: Lang = Query("ru"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_manager_only),
):
    try:
        return await api_service.archive_tx(
            db, elevator_id, actor_user_id=user.id, reason=body.reason, language=lang
        )
    except ElevatorServiceError as exc:
        raise http_error(exc)


@router.put("/{elevator_id}/status", response_model=ElevatorStatusChangeOut)
@limiter.limit("30/minute")
async def set_status(
    request: Request,
    elevator_id: int,
    body: ElevatorStatusIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_staff),
):
    """Смена статуса; ``request_number`` → источник ``request_hint``. Жителям — после commit."""
    try:
        return await api_service.set_status_tx(
            db, elevator_id, status=body.status, reason=body.reason,
            request_number=body.request_number, actor_user_id=user.id,
        )
    except ElevatorServiceError as exc:
        raise http_error(exc)


@router.get("/{elevator_id}/events", response_model=list[ElevatorEventOut])
async def list_events(
    elevator_id: int,
    limit: int = Query(100, ge=1, le=500),
    before_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_staff),
):
    try:
        return await api_service.list_events(db, elevator_id, limit=limit, before_id=before_id)
    except ElevatorServiceError as exc:
        raise http_error(exc)


@router.get("/{elevator_id}/requests", response_model=list[ElevatorRequestRowOut])
async def list_requests(
    elevator_id: int,
    include_closed: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_staff),
):
    try:
        return await api_service.list_requests(db, elevator_id, include_closed=include_closed)
    except ElevatorServiceError as exc:
        raise http_error(exc)
