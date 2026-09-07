"""API-сервис-слой «Лифты»: реестр, паспорт, статус, заявки, конфиг, групповая приёмка.

Доменная логика — в ``services/elevator_service`` (общая с ботом); здесь —
транзакционные обёртки (вызов домена + ``commit``), сборка контекста
страницы одним набором запросов и post-commit-эффекты (рассылка жителям
после смены статуса — best-effort, строго после ``commit``). Доменные
исключения ``ElevatorServiceError`` пролетают наверх — их маппит роутер.
График — ``calendar_service.py``.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api.dependencies import _parse_user_roles
from uk_management_bot.api.residents.notify import send_plain_messages
from uk_management_bot.database.models.elevator import Elevator
from uk_management_bot.database.models.user import User
from uk_management_bot.database.session import AsyncSessionLocal
from uk_management_bot.services import elevator_service as domain
from uk_management_bot.services.elevator_service.grouping import BulkItemResult, bulk_confirm_async
from uk_management_bot.utils.business_time import business_today
from uk_management_bot.utils.datetime_utils import utc_now
from uk_management_bot.utils.http_errors import describe_http_error
from uk_management_bot.utils.request_workflow import PrincipalRef

from . import presenters, queries
from .schemas import (
    ElevatorDetailOut,
    ElevatorEventOut,
    ElevatorListOut,
    ElevatorMiniOut,
    ElevatorRequestRowOut,
    ElevatorStatusChangeOut,
    ElevatorSummaryOut,
    ElevatorsConfigOut,
)

logger = logging.getLogger(__name__)

# Роли, видящие лифты любого дома (жителю — только дома с одобренной квартирой)
STAFF_ROLES: frozenset[str] = frozenset({"executor", "inspector", "manager"})
SOURCE_MANUAL = "manual"
SOURCE_REQUEST_HINT = "request_hint"


@dataclass(frozen=True)
class RegistryQuery:
    """Фильтры реестра из query-строки."""

    yard_id: int | None = None
    building_id: int | None = None
    status: str | None = None
    flags: frozenset[str] = frozenset()
    include_archived: bool = False
    sort: str | None = None
    order: str | None = None
    limit: int = 50
    offset: int = 0


# ── Контекст карточек ────────────────────────────────────────────────

async def _card_context(
    db: AsyncSession, elevators: Sequence[Elevator], *, language: str, now: datetime
) -> presenters.CardContext:
    """Четыре запроса на страницу (доступность, просрочки ТО, заявки, дворы) — без N+1."""
    ids = [elevator.id for elevator in elevators]
    today = business_today(now)
    return presenters.CardContext(
        today=today,
        language=language,
        overdue_ids=await domain.maintenance_overdue_ids_async(db, ids, today=today),
        availability=await domain.availability_30d_for_page_async(db, elevators, now=now),
        open_requests=await domain.count_open_requests_by_elevator_async(db, ids),
        yard_names=await queries.yard_names_by_ids(db, {e.building.yard_id for e in elevators}),
    )


async def _detail_of(db: AsyncSession, elevator: Elevator, *, language: str) -> ElevatorDetailOut:
    ctx = await _card_context(db, [elevator], language=language, now=utc_now())
    without_entrance = await domain.count_building_apartments_without_entrance_async(
        db, elevator.building_id
    )
    return presenters.build_detail(elevator, ctx, apartments_without_entrance_count=without_entrance)


async def _reload_detail(db: AsyncSession, elevator_id: int, *, language: str) -> ElevatorDetailOut:
    """После commit перечитать лифт с домом (свежие server-default/onupdate поля)."""
    elevator = await domain.get_elevator_including_archived_async(db, elevator_id)
    return await _detail_of(db, elevator, language=language)


# ── Чтение ───────────────────────────────────────────────────────────

async def list_page(db: AsyncSession, query: RegistryQuery, *, language: str) -> ElevatorListOut:
    now = utc_now()
    filters = dict(
        yard_id=query.yard_id, building_id=query.building_id, status=query.status,
        include_archived=query.include_archived, flags=set(query.flags), now=now,
    )
    elevators = await domain.list_elevators_async(
        db, limit=query.limit, offset=query.offset, sort=query.sort, order=query.order, **filters
    )
    total = await domain.count_elevators_async(db, **filters)
    ctx = await _card_context(db, elevators, language=language, now=now)
    return ElevatorListOut(items=[presenters.build_card(e, ctx) for e in elevators], total=total)


async def get_detail(db: AsyncSession, elevator_id: int, *, language: str) -> ElevatorDetailOut:
    """Карточка лифта (включая архивный — история должна быть видна персоналу)."""
    return await _reload_detail(db, elevator_id, language=language)


async def summary(db: AsyncSession) -> ElevatorSummaryOut:
    config = await domain.load_config_async(db)
    thresholds = config["downtime_threshold_days"]
    result = await domain.summary_async(db, now=utc_now(), downtime_thresholds=thresholds)
    return presenters.build_summary(result, thresholds)


async def can_view_building(db: AsyncSession, user: User, building_id: int) -> bool:
    """Персонал — любой дом; житель — только дом с одобренной квартирой."""
    if STAFF_ROLES & set(_parse_user_roles(user)):
        return True
    return await queries.has_approved_apartment_in_building(db, user.id, building_id)


async def list_for_building(
    db: AsyncSession, building_id: int, *, language: str
) -> list[ElevatorMiniOut]:
    """Активные и введённые в эксплуатацию лифты дома — для выбора в заявке.

    Р18a: вердикт «жителю запрещено» считает сервер (статус + тумблер конфига),
    чтобы TWA не тянула менеджерский ``/config``. Конфиг читается максимум один
    раз на страницу и ТОЛЬКО если в доме есть лифт под работами — на штатном
    пути (все лифты работают) запроса к ``elevators_config`` нет вовсе.
    """
    elevators = [e for e in await domain.list_active_for_building_async(db, building_id)
                 if e.is_commissioned]
    under_works = any(domain.is_under_works(e.current_status) for e in elevators)
    allowed = (
        domain.resident_requests_allowed(await domain.load_config_async(db))
        if under_works
        else False
    )
    return [
        presenters.build_mini(e, language, resident_requests_under_works_allowed=allowed)
        for e in elevators
    ]


async def list_events(
    db: AsyncSession, elevator_id: int, *, limit: int, before_id: int | None
) -> list[ElevatorEventOut]:
    await domain.get_elevator_including_archived_async(db, elevator_id)  # 404, если нет
    events = await domain.list_events_async(db, elevator_id, limit=limit, before_id=before_id)
    return [presenters.build_event(event) for event in events]


async def list_requests(
    db: AsyncSession, elevator_id: int, *, include_closed: bool
) -> list[ElevatorRequestRowOut]:
    await domain.get_elevator_including_archived_async(db, elevator_id)  # 404, если нет
    rows = await domain.list_requests_for_elevator_async(db, elevator_id, include_closed=include_closed)
    users = await queries.users_by_ids(
        db, [*(r.user_id for r in rows), *(r.executor_id for r in rows)]
    )
    return [presenters.build_request_row(row, users) for row in rows]


# ── Запись: паспорт ──────────────────────────────────────────────────

async def create_tx(
    db: AsyncSession, data: Mapping[str, Any], *, actor_user_id: int, language: str
) -> ElevatorDetailOut:
    elevator = await domain.create_elevator_async(db, data, actor_user_id=actor_user_id)
    await db.commit()
    return await _reload_detail(db, elevator.id, language=language)


async def patch_tx(
    db: AsyncSession, elevator_id: int, patch: Mapping[str, Any], *,
    actor_user_id: int, expected_version: int | None, language: str,
) -> ElevatorDetailOut:
    await domain.update_passport_async(
        db, elevator_id, patch, actor_user_id=actor_user_id, expected_version=expected_version,
    )
    await db.commit()
    return await _reload_detail(db, elevator_id, language=language)


async def commission_tx(
    db: AsyncSession, elevator_id: int, *, actor_user_id: int, commissioned_at, language: str,
) -> ElevatorDetailOut:
    await domain.commission_async(
        db, elevator_id, actor_user_id=actor_user_id, commissioned_at=commissioned_at
    )
    await db.commit()
    return await _reload_detail(db, elevator_id, language=language)


async def archive_tx(
    db: AsyncSession, elevator_id: int, *, actor_user_id: int, reason: str, language: str,
) -> ElevatorDetailOut:
    await domain.archive_async(db, elevator_id, actor_user_id=actor_user_id, reason=reason)
    await db.commit()
    return await _reload_detail(db, elevator_id, language=language)


# ── Запись: статус ───────────────────────────────────────────────────

async def set_status_tx(
    db: AsyncSession, elevator_id: int, *, status: str, reason: str | None,
    request_number: str | None, actor_user_id: int,
) -> ElevatorStatusChangeOut:
    """Смена статуса; уведомления жителям — после commit, best-effort."""
    config = await domain.load_config_async(db)
    change = await domain.set_status_async(
        db, elevator_id, status, actor_user_id=actor_user_id,
        source=SOURCE_REQUEST_HINT if request_number else SOURCE_MANUAL,
        reason=reason, request_number=request_number, config=config,
    )
    await db.commit()
    notified = await _notify_residents(change.resident_messages, elevator_id=elevator_id)
    return ElevatorStatusChangeOut(
        changed=change.changed, old_status=change.old_status, new_status=change.new_status,
        status_since=presenters.aware_utc(change.status_since), notified_residents=notified,
    )


async def _notify_residents(messages: Sequence[Any], *, elevator_id: int) -> int:
    """Рассылка после commit: любой сбой — в лог, статус уже сохранён, 500 недопустим.

    Broad except осознанно (best-effort уведомление, см. правило ратчета
    AUD5-ARCH-5); текст исключения не логируется — httpx-ошибки несут URL с
    токеном бота, поэтому только класс/HTTP-статус (``describe_http_error``).
    """
    if not messages:
        return 0
    try:
        return await send_plain_messages(messages)
    except Exception as exc:  # noqa: BLE001 — best-effort после commit
        logger.error(
            "Рассылка жителям о лифте %s не выполнена: %s", elevator_id, describe_http_error(exc)
        )
        return 0


# ── Конфиг ───────────────────────────────────────────────────────────

async def get_config(db: AsyncSession) -> ElevatorsConfigOut:
    return presenters.build_config(await domain.load_config_async(db))


async def save_config_tx(
    db: AsyncSession, patch: Mapping[str, Any], *, actor_user_id: int
) -> ElevatorsConfigOut:
    merged = await domain.save_config_async(db, patch, actor_user_id=actor_user_id)
    await db.commit()
    return presenters.build_config(merged)


# ── Групповая приёмка ────────────────────────────────────────────────

async def bulk_confirm(
    request_numbers: Sequence[str], *, principal: PrincipalRef
) -> tuple[BulkItemResult, ...]:
    """``MANAGER_CONFIRM`` по списку номеров; runner коммитит сам (своя сессия на команду)."""
    return await bulk_confirm_async(AsyncSessionLocal, request_numbers, principal=principal)
