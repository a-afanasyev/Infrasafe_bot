"""API-сервис-слой визуальных отчётов (AUD5-ARCH-2 волна 5, ARC-05a-канон).

Доменная логика (сага публикации, media-валидация, автозаполнение) остаётся в
`services/work_report_service.py`; здесь — data-access обоих роутеров модуля
(менеджерского и публичного) и транзакционные финализации.

Замечания по границе:
- `locked_report`/`locked_editable_*` берут `with_for_update()` — лок живёт в
  транзакции сессии до commit/rollback вызывающего; проверки статуса и 404/409
  остаются в роутере (см. TOCTOU-комментарий у PATCH).
- `published_page`/`report_by_id` НЕ глотают OperationalError/ProgrammingError —
  graceful-degrade немигрированной таблицы (пустая лента/404) — это
  HTTP-политика публичного роутера.
"""
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from uk_management_bot.constants.work_reports import MEDIA_EDITABLE_STATUSES
from uk_management_bot.database.models.apartment import Apartment
from uk_management_bot.database.models.building import Building
from uk_management_bot.database.models.request import Request as RequestModel
from uk_management_bot.database.models.work_report import WorkReport
from uk_management_bot.database.models.yard import Yard
from uk_management_bot.services import work_report_service


# ── менеджерский роутер ─────────────────────────────────────────────────


async def work_reports_page(
    db: AsyncSession, *, statuses: Optional[list[str]], limit: int, offset: int
):
    """→ (rows, total) отчётов, новые сверху; statuses=None — без фильтра."""
    filters = [WorkReport.status.in_(statuses)] if statuses else []
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
    return rows, total


async def report_by_request_number(db: AsyncSession, request_number: str) -> Optional[WorkReport]:
    return (
        await db.execute(
            select(WorkReport).where(WorkReport.request_number == request_number)
        )
    ).scalar_one_or_none()


async def request_by_number(db: AsyncSession, request_number: str) -> Optional[RequestModel]:
    return (
        await db.execute(
            select(RequestModel).where(RequestModel.request_number == request_number)
        )
    ).scalar_one_or_none()


async def building_with_yard(db: AsyncSession, building_id: int) -> Optional[Building]:
    return (
        await db.execute(
            select(Building)
            .options(selectinload(Building.yard))
            .where(Building.id == building_id)
        )
    ).scalar_one_or_none()


async def yard_by_id(db: AsyncSession, yard_id: int) -> Optional[Yard]:
    return (await db.execute(select(Yard).where(Yard.id == yard_id))).scalar_one_or_none()


async def request_with_address_chain(db: AsyncSession, request_number: str) -> RequestModel:
    """Заявка с eager-load цепочки адреса (как в sync_pending_drafts)."""
    return (
        await db.execute(
            select(RequestModel)
            .options(
                selectinload(RequestModel.building_obj).selectinload(Building.yard),
                selectinload(RequestModel.apartment_obj)
                .selectinload(Apartment.building)
                .selectinload(Building.yard),
                selectinload(RequestModel.yard_obj),
            )
            .where(RequestModel.request_number == request_number)
        )
    ).scalar_one()


async def persist_manual_report(db: AsyncSession, report: WorkReport) -> WorkReport:
    """Ручное создание отчёта: insert + commit + refresh."""
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


async def autofill_candidates(db: AsyncSession, *, limit: int):
    """Кандидаты автозаполнения (id, request_number) БЕЗ лока — сеть идёт до
    лока (AUD6-P1-3), запись — короткой per-report транзакцией ниже."""
    return (
        await db.execute(
            select(WorkReport.id, WorkReport.request_number)
            .where(
                WorkReport.media_synced_at.is_(None),
                WorkReport.status.in_(MEDIA_EDITABLE_STATUSES),
            )
            .order_by(WorkReport.created_at)
            .limit(limit)
        )
    ).all()


async def apply_autofill_locked(
    db: AsyncSession, report_id: int, before_ids: list, after_ids: list
) -> bool:
    """Короткая per-report транзакция автозаполнения: перепроверка статуса под
    `FOR UPDATE`, применение выборки, commit. Уехавшая строка (сага публикации)
    молча пропускается — commit закрывает транзакцию, → False."""
    row = (
        await db.execute(
            select(WorkReport)
            .where(
                WorkReport.id == report_id,
                WorkReport.status.in_(MEDIA_EDITABLE_STATUSES),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        await db.commit()
        return False
    work_report_service.apply_media_selection(row, before_ids, after_ids)
    await db.commit()
    return True


async def locked_report(db: AsyncSession, report_id: int) -> Optional[WorkReport]:
    """Отчёт под `FOR UPDATE` (без фильтра статуса — 404/409 решает роутер).

    Лок обязателен против саги публикации (TOCTOU) — см. комментарий у
    PATCH /{report_id} в router.py."""
    return (
        await db.execute(
            select(WorkReport).where(WorkReport.id == report_id).with_for_update()
        )
    ).scalar_one_or_none()


async def finalize_report(db: AsyncSession, report: WorkReport) -> None:
    """Фиксация изменений залоченного отчёта: commit + refresh."""
    await db.commit()
    await db.refresh(report)


# ── публичный роутер ────────────────────────────────────────────────────


async def published_page(db: AsyncSession, *, limit: int, offset: int):
    """→ (rows, total) опубликованных, свежие сверху.

    Пробрасывает OperationalError/ProgrammingError немигрированной таблицы —
    graceful-degrade (пустая лента) остаётся политикой роутера."""
    total = (
        await db.execute(
            select(func.count())
            .select_from(WorkReport)
            .where(WorkReport.status == "published")
        )
    ).scalar_one()
    rows = (
        (
            await db.execute(
                select(WorkReport)
                .where(WorkReport.status == "published")
                .order_by(WorkReport.published_at.desc(), WorkReport.id.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return rows, total


async def report_by_id(db: AsyncSession, report_id: int) -> Optional[WorkReport]:
    return (
        await db.execute(select(WorkReport).where(WorkReport.id == report_id))
    ).scalar_one_or_none()
