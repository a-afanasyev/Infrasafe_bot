"""Сервис визуальных отчётов «до/после» (публичная витрина резидентов).

Функциональный модуль (не класс) — как `material_service.py`. ~9 функций:

* ``derive_public_address`` — чистый резолвер публичного адреса;
* ``sync_pending_drafts`` — автосинхронизация черновиков из завершённых заявок;
* ``autofill_media`` / ``validate_media_ids`` — автозаполнение и ручная
  валидация медиа;
* ``revoke_stale_publications`` — снятие публикации с заявок, переставших
  быть eligible;
* ``publish_report`` / ``unpublish_report`` / ``reject_report`` /
  ``reopen_report`` / ``reconcile_publication_locks`` — сага публикации,
  координирующая состояние между БД бота (`work_reports`) и отдельной БД
  media-service (`media_files`) БЕЗ two-phase commit. Именно эта пятёрка
  несёт основной риск модуля: баг здесь может либо опубликовать контент, не
  прошедший модерацию, либо навсегда «подвесить» медиа в залоченном
  состоянии. Порядок операций внутри каждой функции — часть контракта, не
  стилистика; см. docstring каждой функции.

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
* Сага публикации не использует two-phase commit между двумя БД: вместо
  этого — строго упорядоченные шаги с компенсацией (publish_report) и
  идемпотентная фоновая сверка (reconcile_publication_locks) как
  self-healing на случай крэша посреди саги.
"""

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql as pg_dialect
from sqlalchemy.dialects import sqlite as sqlite_dialect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from uk_management_bot.api.board_config.service import load_board_config
from uk_management_bot.config.settings import settings
from uk_management_bot.constants.work_reports import LOCK_HOLDING_STATUSES
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.work_report import WorkReport
from uk_management_bot.services.request_address import (
    format_building_address,
    format_yard_address,
)
from uk_management_bot.utils.workflow_predicates import (
    is_report_eligible,
    report_eligible_clause,
)

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


class WorkReportPublishError(WorkReportServiceError):
    """Raised by the publication saga (publish/unpublish/reject/reopen) when
    the requested transition can't happen right now. `status_code` carries the
    HTTP semantics a router should use directly — mirrors
    `request_address.AddressResolutionError`'s shape (message + status_code),
    an established pattern in this codebase for service errors a router just
    re-raises as HTTPException.

    404 — the report doesn't exist.
    409 — wrong current status for this transition, OR the underlying request
    stopped being eligible (deleted/status changed/returned) — a conflict with
    current server state, not a defect in the request body.
    422 — the report is missing before/after media, or a media id fails
    re-validation — a defect in what's being published, reachable via manual
    API calls that bypass autofill's own needs_media gating.
    """

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ===========================================================================
# Circuit breaker / floor constants
# ===========================================================================

_SYNC_CANDIDATE_LIMIT = 50
_SYNC_CIRCUIT_BREAKER_LIMIT = 200
_SYNC_MAX_BACKFILL_DAYS = 14

MAX_MEDIA_PER_SIDE = 4
_AUTOFILL_FETCH_LIMIT = MAX_MEDIA_PER_SIDE * 4
_VALIDATE_FETCH_LIMIT = 200

# Статусы, в которых отчёт СЧИТАЕТСЯ держателем publication-lock'ов из своего
# `locked_media_ids`. `needs_review` включён наравне с published/publishing: он
# получается автоматической ревокацией (`revoke_stale_publications`), которая
# не ходит в media-service и локи не снимает, а отчёт может вернуться в ленту
# (unpublish → reopen → publish). Если бы `needs_review` тут не значился,
# `reconcile_publication_locks` счёл бы его локи осиротевшими и снял их, оставив
# `locked_media_ids` лгать о реальном состоянии media-service.
# AUD6-P2-57: значение — из канона constants/work_reports.py.
_LOCK_HOLDING_STATUSES = LOCK_HOLDING_STATUSES


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


_APARTMENT_MARKER_PATTERN = re.compile(r"кв\.?\s*\d", re.IGNORECASE)


def address_looks_like_apartment(address: str) -> bool:
    """Fail-closed heuristic: True if the string contains an apartment-number
    marker (e.g. "кв. 42", "кв42", "Кв. 7"). This is a REJECT guard, not a
    cleaner — legacy free-text address data spans years of manual entry and a
    regex "fix-up" risks a false negative that publishes an apartment number
    irreversibly; false positives (rejecting something safe) are the
    acceptable failure mode here, not false negatives."""
    return bool(_APARTMENT_MARKER_PATTERN.search(address))


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


async def fetch_media_selection(
    media_client: Any, request_number: str
) -> tuple[list[int], list[int]]:
    """СЕТЕВАЯ половина автозаполнения: два GET в media-service + фильтрация.

    AUD6-P1-3: выделена из `autofill_media`, чтобы батч-вызыватели могли
    сходить в сеть ДО взятия row-лока — сеть и запись одной функцией
    вынуждали держать транзакцию с локами через HTTP-таймауты (30 с × 3
    ретрая на вызов). БД не трогает вовсе.
    """
    before_raw = await media_client.get_request_media(
        request_number, category="request_photo", limit=_AUTOFILL_FETCH_LIMIT
    )
    after_raw = await media_client.get_request_media(
        request_number, category="completion_photo", limit=_AUTOFILL_FETCH_LIMIT
    )
    return _filter_and_cap(before_raw), _filter_and_cap(after_raw)


def apply_media_selection(
    report: WorkReport, before_ids: list[int], after_ids: list[int]
) -> WorkReport:
    """ПИШУЩАЯ половина автозаполнения: мутация полей отчёта, без сети и
    без commit (транзакционные границы — на вызывающем).

    Перещёлкивает status pending<->needs_media по факту непустоты результата;
    любой другой статус (publishing/published/needs_review/rejected) не трогает.
    """
    report.before_media_ids = before_ids
    report.after_media_ids = after_ids
    report.media_synced_at = datetime.now(timezone.utc)

    # Обязателен ТОЛЬКО результат (решение владельца 2026-07-25): «до» часто
    # физически нет — житель снял уже текущее состояние, исполнитель приехал на
    # аварию без времени фотографировать. Раньше такой отчёт застревал в
    # needs_media и работа не попадала в ленту вовсе, хотя результат был.
    # Отсутствующее «до» витрина честно показывает подписью «нет фото».
    result_present = bool(report.after_media_ids)
    if not result_present and report.status == "pending":
        report.status = "needs_media"
    elif result_present and report.status == "needs_media":
        report.status = "pending"

    return report


async def autofill_media(db: AsyncSession, media_client: Any, report: WorkReport) -> WorkReport:
    """Подтянуть текущие метаданные из media-service по `report.request_number`,
    отфильтровать подходящие фото, разложить по before/after, обновить поля
    отчёта НА МЕСТЕ (мутирует и возвращает переданный объект — commit НЕ
    делает, транзакционные границы — на вызывающем).

    Композиция `fetch_media_selection` (сеть) + `apply_media_selection`
    (запись): единичным вызовам удобна одной функцией, батчи используют
    половины напрямую, чтобы не держать сеть под локом (AUD6-P1-3).

    Не доверяет никакому предыдущему состоянию `report` — всегда перечитывает
    из media-service. Молчаливая фильтрация здесь осознанна: это автоматический
    подбор из всего доступного, а не явный выбор человека (контраст —
    `validate_media_ids` ниже, который на тех же условиях REJECTS).
    """
    before_ids, after_ids = await fetch_media_selection(
        media_client, report.request_number
    )
    return apply_media_selection(report, before_ids, after_ids)


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


# ===========================================================================
# Publication saga: publish_report / unpublish_report / reject_report /
# reopen_report / reconcile_publication_locks
# ===========================================================================


async def _load_report_for_update(db: AsyncSession, report_id: int) -> WorkReport:
    """Common prefix of every saga transition: lock the report row
    (``FOR UPDATE``, serializes concurrent transitions on the SAME report)
    and 404 if it doesn't exist. The status check and everything after it
    genuinely differ per transition and stay in the caller."""
    report = (
        await db.execute(
            select(WorkReport).where(WorkReport.id == report_id).with_for_update()
        )
    ).scalar_one_or_none()
    if report is None:
        raise WorkReportPublishError(f"work report {report_id} not found", 404)
    return report


async def publish_report(
    db: AsyncSession,
    media_client: Any,
    report_id: int,
    moderator_id: Optional[int],
    *,
    automatic: bool = False,
) -> WorkReport:
    """``pending`` → ``publishing`` (transient) → ``published``.

    `automatic=True` — публикация без модерации (`autopublish`, см.
    `autopublish_ready_drafts`). Меняет ТОЛЬКО аудит-след: действие
    `work_report.autopublish` вместо `work_report.publish`, и `moderated_by`
    остаётся пустым. Так по журналу видно, что содержимое фотографий человек не
    подтверждал — для «отчётности проверяющим органам» это существенная разница,
    и подменять её именем менеджера, который всего лишь включил тумблер, нельзя.
    Все проверки безопасности (eligibility, адрес, обе стороны фото,
    перевалидация медиа, publication-lock) идентичны — режим их не ослабляет.

    Ordering is load-bearing — do not reorder steps:

    1. Lock the report row (``FOR UPDATE``) — serializes concurrent publish
       attempts on the SAME report.
    2. Re-check the underlying request still exists and is eligible — the
       last gate before content goes public.
    3. Re-check the public address is still safe (defense in depth — should
       already hold from creation time).
    4. Require the result media side be non-empty.
    5. Flip to ``publishing`` and commit — NOT publicly visible yet (a public
       feed filters strictly on ``status == "published"``), but this makes
       the report ineligible for a second concurrent publish attempt AND
       freezes its media composition (PATCH/autofill only touch
       ``pending``/``needs_media``). The row lock is released here — held
       only across cheap local checks, never across the network.
    6. Re-validate every media id against CURRENT media-service metadata —
       WITHOUT the row lock (AUD6-P1-3: this is up to two HTTP calls of
       30 s × 3 retries each; holding row locks and a pool connection in an
       open transaction across that was the exact class that already caused
       the media-service pool-exhaustion incident). The transient status is
       protection enough. On failure, compensate: revert to ``pending``,
       raise 422.
    7. Acquire a publication lock per media id, SEQUENTIALLY, committing
       ``locked_media_ids`` after EVERY successful acquire so the on-disk
       state always matches what's actually locked in media-service even if
       the process crashes mid-loop. On the first failure, compensate: release
       every lock acquired in THIS attempt, revert to ``pending``, raise 409.
    8. Snapshot media metadata for the now-locked ids.
    9. Flip to ``published``, stamp moderation fields, write an audit log,
       commit.

    A crash between steps 5 and 9 leaves the report stuck in ``publishing``
    (correctly invisible publicly) with ``locked_media_ids`` accurately
    reflecting what's locked — that's what ``reconcile_publication_locks``
    is for.
    """
    report = await _load_report_for_update(db, report_id)
    if report.status != "pending":
        raise WorkReportPublishError(
            f"work report {report_id} is {report.status}, expected pending", 409
        )

    request = (
        await db.execute(
            select(Request).where(Request.request_number == report.request_number)
        )
    ).scalar_one_or_none()
    if request is None or not is_report_eligible(request):
        raise WorkReportPublishError(
            f"request {report.request_number} no longer eligible", 409
        )

    if not report.address_public or address_looks_like_apartment(report.address_public):
        raise WorkReportPublishError(
            f"work report {report_id} has an invalid public address", 409
        )

    # Фото РЕЗУЛЬТАТА обязательно, «до» — нет (решение владельца 2026-07-25).
    # Отчёт без результата публиковать нечему: карточка «работы выполнены» без
    # единого доказательства — это не отчёт. Отсутствующее «до» витрина
    # показывает подписью «нет фото», и это честнее, чем скрывать работу целиком.
    if not report.after_media_ids:
        raise WorkReportPublishError(
            f"work report {report_id} is missing result media", 422
        )

    report.status = "publishing"
    report.state_changed_at = datetime.now(timezone.utc)
    await db.commit()

    # Шаг 6: сеть — УЖЕ без row-лока (см. docstring). Состав медиа заморожен
    # статусом `publishing`, так что валидируем ровно те id, что опубликуем.
    # Компенсация на ЛЮБОЙ сбой, включая транспортный: до этого шага не взят
    # ни один publication-lock, значит откат в `pending` всегда безопасен, и
    # парковать отчёт в `publishing` до reconcile здесь незачем.
    try:
        await validate_media_ids(
            media_client, report.request_number, report.before_media_ids, report.after_media_ids
        )
    except Exception as e:
        report.status = "pending"
        report.state_changed_at = datetime.now(timezone.utc)
        await db.commit()
        if isinstance(e, MediaValidationError):
            raise WorkReportPublishError(str(e), 422) from e
        raise

    all_media_ids = list(report.before_media_ids) + list(report.after_media_ids)
    acquired: list[int] = []
    for media_id in all_media_ids:
        ok = await media_client.acquire_publication_lock(media_id)
        if not ok:
            for locked_id in acquired:
                await media_client.release_publication_lock(locked_id)
            report.locked_media_ids = []
            report.status = "pending"
            report.state_changed_at = datetime.now(timezone.utc)
            await db.commit()
            raise WorkReportPublishError(
                f"could not acquire publication lock for media {media_id}", 409
            )
        acquired.append(media_id)
        report.locked_media_ids = list(acquired)
        await db.commit()

    before_meta = {
        item["id"]: item
        for item in await media_client.get_request_media(
            report.request_number, category="request_photo", limit=_VALIDATE_FETCH_LIMIT
        )
    }
    after_meta = {
        item["id"]: item
        for item in await media_client.get_request_media(
            report.request_number, category="completion_photo", limit=_VALIDATE_FETCH_LIMIT
        )
    }
    combined_meta = {**before_meta, **after_meta}
    media_meta = [
        {
            "id": media_id,
            "file_type": "photo",
            "mime": combined_meta[media_id]["mime_type"],
            "size": combined_meta[media_id]["file_size"],
        }
        for media_id in acquired
    ]

    report.media_meta = media_meta
    report.status = "published"
    report.published_at = datetime.now(timezone.utc)
    report.moderated_by = None if automatic else moderator_id
    db.add(AuditLog(
        user_id=None if automatic else moderator_id,
        action="work_report.autopublish" if automatic else "work_report.publish",
        details={
            "report_id": report.id,
            "request_number": report.request_number,
            "before_ids": report.before_media_ids,
            "after_ids": report.after_media_ids,
            # Кто включил режим — не то же самое, что «кто одобрил контент».
            # Пишем отдельным ключом, чтобы журнал не выглядел как одобрение.
            **({"triggered_by": moderator_id} if automatic else {}),
        },
    ))
    await db.commit()

    # Прогрев превью — ПОСЛЕ коммита и best-effort: отчёт уже опубликован, и
    # неудача оптимизации не должна его откатывать. Здесь же, а не только в
    # тике, потому что менеджер часто смотрит витрину сразу после публикации, а
    # тик придёт лишь через 10 минут.
    await warm_report_previews(media_client, report)
    return report


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


_AUTOPUBLISH_BATCH_LIMIT = 20
# AUD6-P1-3: потолок времени на пакет автопубликации. При деградировавшем
# media-service каждый отчёт может стоить до ~90 с сетевых таймаутов — без
# потолка пакет из 20 растягивался на десятки минут внутри /sync и тика.
_AUTOPUBLISH_TIME_BUDGET_SECONDS = 60.0


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
            .limit(_AUTOPUBLISH_BATCH_LIMIT)
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
    deadline = time.monotonic() + _AUTOPUBLISH_TIME_BUDGET_SECONDS

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
            before_ids, after_ids = await fetch_media_selection(
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
        apply_media_selection(row, before_ids, after_ids)
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
            await publish_report(db, media_client, report_id, triggered_by, automatic=True)
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


async def unpublish_report(
    db: AsyncSession,
    media_client: Any,
    report_id: int,
    moderator_id: int,
    reason: Optional[str] = None,
) -> WorkReport:
    """``published``/``needs_review`` → ``rejected``.

    Order matters for safety: hide in the UK database FIRST (commit), THEN
    release media locks — never the other way around. The failure-safe
    direction is "an extra lock lingers" (annoying, file can't be archived
    yet), not "a public report exists whose photo bytes have no lock
    guarantee" (a real privacy/correctness problem).
    """
    report = await _load_report_for_update(db, report_id)
    if report.status not in ("published", "needs_review"):
        raise WorkReportPublishError(
            f"work report {report_id} is {report.status}, expected published or needs_review",
            409,
        )

    media_ids_to_release = list(report.locked_media_ids)
    report.status = "rejected"
    report.reject_reason = reason or report.reject_reason
    report.moderated_by = moderator_id
    report.state_changed_at = datetime.now(timezone.utc)
    report.locked_media_ids = []
    db.add(AuditLog(
        user_id=moderator_id,
        action="work_report.unpublish",
        details={"report_id": report.id, "request_number": report.request_number, "reason": reason},
    ))
    await db.commit()  # DB-side hidden FIRST — see docstring on why this ordering is load-bearing

    # A media id shared with another still-live report (see
    # _LOCK_HOLDING_STATUSES) must stay locked. Small expected scale
    # (concurrently live publications, not raw media rows) — plain Python set
    # membership over loaded rows avoids fragile dialect-specific
    # JSON-array-containment SQL (Postgres JSONB @>/? vs SQLite json_each are
    # not the same code).
    other_locked: set[int] = set()
    other_rows = (await db.execute(
        select(WorkReport.locked_media_ids).where(
            WorkReport.id != report.id,
            WorkReport.status.in_(_LOCK_HOLDING_STATUSES),
        )
    )).all()
    for (ids,) in other_rows:
        other_locked.update(ids or [])

    for media_id in media_ids_to_release:
        if media_id in other_locked:
            continue
        await media_client.release_publication_lock(media_id)

    return report


async def reject_report(
    db: AsyncSession, report_id: int, moderator_id: int, reason: str
) -> WorkReport:
    """``pending``/``needs_media`` → ``rejected``.

    No media locks exist yet at this stage (the report was never published),
    so this is a plain status transition + audit log, no media-service
    interaction.
    """
    report = await _load_report_for_update(db, report_id)
    if report.status not in ("pending", "needs_media"):
        raise WorkReportPublishError(
            f"work report {report_id} is {report.status}, expected pending or needs_media",
            409,
        )
    report.status = "rejected"
    report.reject_reason = reason
    report.moderated_by = moderator_id
    report.state_changed_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        user_id=moderator_id,
        action="work_report.reject",
        details={"report_id": report.id, "request_number": report.request_number, "reason": reason},
    ))
    await db.commit()
    return report


async def reopen_report(db: AsyncSession, report_id: int, moderator_id: int) -> WorkReport:
    """``rejected`` → ``pending``."""
    report = await _load_report_for_update(db, report_id)
    if report.status != "rejected":
        raise WorkReportPublishError(
            f"work report {report_id} is {report.status}, expected rejected", 409
        )
    report.status = "pending"
    report.reject_reason = None
    report.state_changed_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        user_id=moderator_id,
        action="work_report.reopen",
        details={"report_id": report.id, "request_number": report.request_number},
    ))
    await db.commit()
    return report


_RECONCILE_STALE_MINUTES = 15


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
        select(WorkReport.locked_media_ids).where(WorkReport.status.in_(_LOCK_HOLDING_STATUSES))
    )).all()
    for (ids,) in live_rows:
        covered_ids.update(ids or [])

    orphaned = inventory_ids - covered_ids
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
        "missing_locks_relocked": relocked,
        "stale_transitions": stale_transitions,
    }
