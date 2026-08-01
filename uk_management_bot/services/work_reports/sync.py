"""Автосинхронизация черновиков из завершённых заявок (`sync_pending_drafts`)
и снятие публикации с заявок, переставших быть eligible
(`revoke_stale_publications`)."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql as pg_dialect
from sqlalchemy.dialects import sqlite as sqlite_dialect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from uk_management_bot.api.board_config.service import load_board_config
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.work_report import WorkReport
from uk_management_bot.utils.workflow_predicates import report_eligible_clause

logger = logging.getLogger(__name__)

_SYNC_CANDIDATE_LIMIT = 50
_SYNC_CIRCUIT_BREAKER_LIMIT = 200
_SYNC_MAX_BACKFILL_DAYS = 14


def _svc():
    """Ленивое обращение к фасаду `services.work_report_service`: тесты и
    колл-сайты патчат атрибуты по имени фасада, поэтому межмодульные вызовы
    внутри пакета идут через него (см. докстринг пакета)."""
    from uk_management_bot.services import work_report_service

    return work_report_service


# ===========================================================================
# sync_pending_drafts
# ===========================================================================


def _sync_insert_stmt(dialect_name: str, values: dict):
    """ARCH-010-паттерн (webhook_sender._outbox_insert_stmt): dialect-aware
    ``INSERT ... ON CONFLICT (request_number) DO NOTHING`` — делает двойной
    вызов sync (два воркера/повторный прогон) безопасным no-op'ом, а не
    IntegrityError. `sqlalchemy.insert()` generic не имеет
    `.on_conflict_do_nothing()` — нужен диалект-специфичный insert."""
    insert_fn = pg_dialect.insert if dialect_name == "postgresql" else sqlite_dialect.insert
    return insert_fn(WorkReport).values(**values).on_conflict_do_nothing(
        index_elements=["request_number"]
    )


async def sync_pending_drafts(db: AsyncSession) -> dict:
    """Автосоздать `WorkReport`-черновики (status="pending", source="auto")
    из подходящих завершённых заявок, идемпотентно.

    Владеет своей транзакцией (commit внутри) — самодостаточная
    maintenance-операция, а не часть чужого рабочего юнита.

    Фильтр категорий здесь НЕ применяется — он живёт только в
    `autopublish_ready_drafts` (см. комментарий у цикла ниже).
    """
    cfg = await load_board_config(db)
    if not cfg.work_reports.autopost:
        return {"created": 0, "circuit_breaker": False}

    pending_count = (
        await db.execute(
            select(func.count()).select_from(WorkReport).where(
                WorkReport.status.in_(("pending", "needs_media"))
            )
        )
    ).scalar_one()
    if pending_count >= _SYNC_CIRCUIT_BREAKER_LIMIT:
        logger.warning(
            "sync_pending_drafts: circuit breaker сработал — %d черновиков в "
            "pending/needs_media (лимит %d), пропускаю синк",
            pending_count, _SYNC_CIRCUIT_BREAKER_LIMIT,
        )
        return {"created": 0, "circuit_breaker": True}

    now = datetime.now(timezone.utc)
    # autopost_since не должен быть None к этому моменту (стамп на переходе
    # False→True в merge_and_save_board_config), но fallback на "сейчас" —
    # самый консервативный вариант (не бэкфиллить неизвестную историю).
    autopost_since = cfg.work_reports.autopost_since or now
    floor_ts = max(autopost_since, now - timedelta(days=_SYNC_MAX_BACKFILL_DAYS))

    anchor = func.coalesce(Request.completed_at, Request.updated_at, Request.created_at)
    already_synced = (
        select(WorkReport.request_number)
        .where(WorkReport.request_number == Request.request_number)
        .correlate(Request)
        .exists()
    )
    stmt = (
        select(Request)
        .options(
            selectinload(Request.building_obj).selectinload(Building.yard),
            selectinload(Request.apartment_obj)
            .selectinload(Apartment.building)
            .selectinload(Building.yard),
            selectinload(Request.yard_obj),
        )
        .where(
            report_eligible_clause(),
            Request.address_type.in_(("apartment", "building", "yard")),
            anchor >= floor_ts,
            ~already_synced,
        )
        .order_by(anchor.desc())
        .limit(_SYNC_CANDIDATE_LIMIT)
    )
    candidates = (await db.execute(stmt)).scalars().all()

    # Ленивый импорт — как в остальном репо (api/requests/schemas.py,
    # api/requests/stats_router.py): keyboards.requests тянет aiogram.types.
    from uk_management_bot.keyboards.requests import resolve_category_key

    dialect_name = db.get_bind().dialect.name
    # `cfg.work_reports.categories` здесь СОЗНАТЕЛЬНО не применяется: список
    # ограничивает автоматику публикации (`autopublish_ready_drafts`), а не
    # попадание заявки в очередь модерации. Фильтр стоял здесь и делал обратное —
    # заявка вне списка не получала черновика вовсе, а это необратимо: она
    # уезжает из 14-дневного окна `floor_ts`, и снятие галочки её уже не вернёт
    # (в отличие от черновика, который просто лежит в очереди). Плюс это
    # расходилось с подписью в UI, обещающей «остальные отчёты остаются на
    # модерации». Черновик создаётся для любой подходящей заявки; что уйдёт в
    # ленту без человека — решает фильтр в автопубликации.
    created = 0
    for r in candidates:
        category_key = resolve_category_key(r.category)
        address = _svc().derive_public_address(r)
        if address is None:
            logger.warning(
                "sync_pending_drafts: derive_public_address вернул None для "
                "%s (address_type=%s) — пропускаю, не создаю битую строку",
                r.request_number, r.address_type,
            )
            continue
        performed_at = r.completed_at or r.updated_at or r.created_at
        values = {
            "request_number": r.request_number,
            "category_key": category_key,
            "address_public": address,
            "performed_at": performed_at,
            "status": "pending",
            "source": "auto",
        }
        result = await db.execute(_sync_insert_stmt(dialect_name, values))
        if result.rowcount == 1:
            created += 1

    await db.commit()
    return {"created": created, "circuit_breaker": False}


# ===========================================================================
# revoke_stale_publications
# ===========================================================================


async def revoke_stale_publications(db: AsyncSession) -> int:
    """Опубликованные отчёты, чья заявка ещё СУЩЕСТВУЕТ, но перестала
    удовлетворять условиям eligibility (статус ушёл от Исполнено/Принято,
    либо is_returned стал true), переводятся в needs_review с аудит-следом.

    Жёстко удалённые заявки НЕ трогаются — INNER JOIN к `requests` их
    естественным образом исключает (сравнивать не с чем), это осознанное
    поведение, не недосмотр: снимок отчёта обязан пережить удаление заявки.

    Владеет своей транзакцией (commit внутри).
    """
    stmt = (
        select(WorkReport, Request.status, Request.is_returned)
        .join(Request, Request.request_number == WorkReport.request_number)
        .where(
            WorkReport.status == "published",
            ~report_eligible_clause(),
        )
    )
    rows = (await db.execute(stmt)).all()
    now = datetime.now(timezone.utc)
    for report, request_status, is_returned in rows:
        report.status = "needs_review"
        report.reject_reason = "request_no_longer_eligible"
        report.state_changed_at = now
        db.add(AuditLog(
            user_id=None,
            action="work_report.revoked",
            details={
                "report_id": report.id,
                "request_number": report.request_number,
                "request_status": request_status,
                "is_returned": is_returned,
            },
        ))
    await db.commit()
    return len(rows)
