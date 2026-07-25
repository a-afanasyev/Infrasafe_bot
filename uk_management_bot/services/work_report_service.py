"""Сервис визуальных отчётов «до/после» (публичная витрина резидентов).

Функциональный модуль (не класс) — как `material_service.py`. Эта задача
строит 4 из ~9 итоговых функций модуля: чистый резолвер публичного адреса,
автосинхронизацию черновиков из завершённых заявок, автозаполнение/валидацию
медиа и снятие публикации с заявок, переставших быть eligible. Сага публикации
(``publish_report``/``unpublish_report``/``reject_report``/``reopen_report``/
``reconcile_publication_locks``) — отдельная задача, дописывается в этот же
файл.

Инварианты (см. также database/models/work_report.py):

* ``WorkReport.request_number`` — НЕ FK: заявку можно жёстко удалить, отчёт —
  бессрочный снапшот и обязан её пережить. Отсюда: синк — dialect-aware
  ``INSERT ... ON CONFLICT DO NOTHING`` (паттерн ``webhook_sender.
  _outbox_insert_stmt``), а не ORM-relationship; сверка публикаций — INNER
  JOIN к `requests`, где отсутствие строки-заявки — не сигнал к действию.
* Автозаполнение медиа (`autofill_media`) фильтрует молча — это автоматический
  подбор кандидатов, не выбор человека. Ручная валидация (`validate_media_ids`)
  на тех же условиях — REJECTS, потому что выбор сделал человек и тихий
  дроп был бы неверной реакцией на его ошибку.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql as pg_dialect
from sqlalchemy.dialects import sqlite as sqlite_dialect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from uk_management_bot.api.board_config.service import load_board_config
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.work_report import WorkReport
from uk_management_bot.services.request_address import (
    format_building_address,
    format_yard_address,
)
from uk_management_bot.utils.workflow_predicates import report_eligible_clause

logger = logging.getLogger(__name__)

# ===========================================================================
# Ошибки
# ===========================================================================


class WorkReportServiceError(Exception):
    """База ошибок work_report_service."""


class MediaValidationError(WorkReportServiceError):
    """Media id, явно выбранный человеком, не прошёл проверку по текущим
    метаданным media-service (не относится к заявке/категории, не фото, не
    активен, слишком большой или размер неизвестен).

    Используется там, где выбор сделал человек (ручной PATCH, повторная
    проверка перед публикацией) и тихий дроп был бы неверной реакцией на его
    ошибку. Контраст с `autofill_media` ниже, который молча фильтрует
    автоматически найденных кандидатов."""


# ===========================================================================
# Circuit breaker / floor constants
# ===========================================================================

_SYNC_CANDIDATE_LIMIT = 50
_SYNC_CIRCUIT_BREAKER_LIMIT = 200
_SYNC_MAX_BACKFILL_DAYS = 14

MAX_MEDIA_PER_SIDE = 4
_AUTOFILL_FETCH_LIMIT = MAX_MEDIA_PER_SIDE * 4
_VALIDATE_FETCH_LIMIT = 200


# ===========================================================================
# derive_public_address — pure, без I/O
# ===========================================================================


def derive_public_address(request: Request) -> Optional[str]:
    """Анонимизированный адрес для публичной витрины.

    НИКОГДА не копия `Request.address` (та хранит ", кв. N" для квартир).
    Заявки уровня дом/двор используют собственный канонический форматтер;
    заявки уровня квартира намеренно пере-выводятся из РОДИТЕЛЬСКОГО ДОМА
    (`format_building_address`, а не `format_apartment_address`, который
    включил бы номер квартиры). legacy/NULL address_type всегда даёт None
    (ручные work-report'ы для них требуют явного building_id/yard_id
    override — забота будущей задачи).

    Вызывающий обязан заранее (eager) загрузить `request.building_obj.yard`,
    `request.apartment_obj.building.yard`, `request.yard_obj` — эта функция
    никогда не должна триггерить lazy-load (async SQLAlchemy на нём падает).
    """
    if request.address_type == "building" and request.building_obj is not None:
        return format_building_address(request.building_obj)
    if (
        request.address_type == "apartment"
        and request.apartment_obj is not None
        and request.apartment_obj.building is not None
    ):
        return format_building_address(request.apartment_obj.building)
    if request.address_type == "yard" and request.yard_obj is not None:
        return format_yard_address(request.yard_obj)
    return None


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
    created = 0
    for r in candidates:
        address = derive_public_address(r)
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
            "category_key": resolve_category_key(r.category),
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
# autofill_media / validate_media_ids
# ===========================================================================


def _filter_and_cap(items: list[dict]) -> list[int]:
    """Молча отфильтровать неподходящие элементы и оставить первые
    MAX_MEDIA_PER_SIDE (без переупорядочивания — порядок, как вернул
    media-service)."""
    eligible = [
        item for item in items
        if item.get("file_type") == "photo"
        and item.get("status") == "active"
        and item.get("file_size") is not None
        and item["file_size"] <= settings.PUBLIC_MEDIA_MAX_BYTES
    ]
    return [item["id"] for item in eligible[:MAX_MEDIA_PER_SIDE]]


async def autofill_media(db: AsyncSession, media_client: Any, report: WorkReport) -> WorkReport:
    """Подтянуть текущие метаданные из media-service по `report.request_number`,
    отфильтровать подходящие фото, разложить по before/after, обновить поля
    отчёта НА МЕСТЕ (мутирует и возвращает переданный объект — commit НЕ
    делает, транзакционные границы — на вызывающем: у единичного и batch-
    автозаполнения из будущих API-эндпоинтов они разные).

    Не доверяет никакому предыдущему состоянию `report` — всегда перечитывает
    из media-service. Молчаливая фильтрация здесь осознанна: это автоматический
    подбор из всего доступного, а не явный выбор человека (контраст —
    `validate_media_ids` ниже, который на тех же условиях REJECTS).

    Перещёлкивает status pending<->needs_media по факту непустоты обеих
    сторон; любой другой статус (publishing/published/needs_review/rejected)
    не трогает.
    """
    before_raw = await media_client.get_request_media(
        report.request_number, category="request_photo", limit=_AUTOFILL_FETCH_LIMIT
    )
    after_raw = await media_client.get_request_media(
        report.request_number, category="completion_photo", limit=_AUTOFILL_FETCH_LIMIT
    )

    report.before_media_ids = _filter_and_cap(before_raw)
    report.after_media_ids = _filter_and_cap(after_raw)
    report.media_synced_at = datetime.now(timezone.utc)

    both_sides_present = bool(report.before_media_ids) and bool(report.after_media_ids)
    if not both_sides_present and report.status == "pending":
        report.status = "needs_media"
    elif both_sides_present and report.status == "needs_media":
        report.status = "pending"

    return report


async def validate_media_ids(
    media_client: Any,
    request_number: str,
    before_media_ids: list[int],
    after_media_ids: list[int],
) -> None:
    """Проверить явно выбранные человеком id против ТЕКУЩИХ метаданных
    media-service (никогда не доверять id вслепую, даже уже выбранным ранее
    менеджером). Бросает `MediaValidationError` на первом невалидном id —
    список НЕ фильтруется и не возвращается: весь смысл — REJECT-ить
    неверный выбор человека, а не тихо его подправить (контраст с
    `autofill_media`, который фильтрует молча).

    Используется ручным PATCH и повторной проверкой перед публикацией — оба
    случая, где решение принял человек и заслуживает явного отказа.
    """
    before_actual = {
        item["id"]: item
        for item in await media_client.get_request_media(
            request_number, category="request_photo", limit=_VALIDATE_FETCH_LIMIT
        )
    }
    after_actual = {
        item["id"]: item
        for item in await media_client.get_request_media(
            request_number, category="completion_photo", limit=_VALIDATE_FETCH_LIMIT
        )
    }

    def _check(media_ids: list[int], actual: dict, side: str) -> None:
        for media_id in media_ids:
            item = actual.get(media_id)
            if item is None:
                raise MediaValidationError(
                    f"media {media_id} does not belong to request {request_number} ({side})"
                )
            if item.get("file_type") != "photo":
                raise MediaValidationError(f"media {media_id} is not a photo")
            if item.get("status") != "active":
                raise MediaValidationError(f"media {media_id} is not active")
            size = item.get("file_size")
            if size is None or size > settings.PUBLIC_MEDIA_MAX_BYTES:
                raise MediaValidationError(
                    f"media {media_id} has unknown or excessive file size"
                )

    _check(before_media_ids, before_actual, "before")
    _check(after_media_ids, after_actual, "after")


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
