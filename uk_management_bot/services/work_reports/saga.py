"""Сага публикации: publish_report / unpublish_report / reject_report /
reopen_report. Порядок операций внутри каждой функции — часть контракта, не
стилистика (см. докстринги)."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.audit import AuditLog
from uk_management_bot.database.models.request import Request
from uk_management_bot.database.models.work_report import WorkReport
from uk_management_bot.services.work_reports.errors import (
    MediaValidationError,
    WorkReportPublishError,
)
from uk_management_bot.services.work_reports.media_selection import _VALIDATE_FETCH_LIMIT
from uk_management_bot.utils.workflow_predicates import is_report_eligible

logger = logging.getLogger(__name__)


def _svc():
    """Ленивое обращение к фасаду `services.work_report_service`: тесты и
    колл-сайты патчат атрибуты по имени фасада, поэтому межмодульные вызовы
    внутри пакета идут через него (см. докстринг пакета)."""
    from uk_management_bot.services import work_report_service

    return work_report_service


# ===========================================================================
# Publication saga: publish_report / unpublish_report / reject_report /
# reopen_report
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

    if not report.address_public or _svc().address_looks_like_apartment(report.address_public):
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
        await _svc().validate_media_ids(
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
    await _svc().warm_report_previews(media_client, report)
    return report


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
            WorkReport.status.in_(_svc()._LOCK_HOLDING_STATUSES),
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
