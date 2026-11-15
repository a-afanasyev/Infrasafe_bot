"""Жизненный цикл записи ``notices``: черновик → опубликована → закрыта.

Видимость жителям — производная от статуса и времени (``visible_clause``):
опубликована, срок публикации наступил, срок показа не истёк. Отдельного
статуса «запланирована» нет — это published с ``publish_at`` в будущем.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.database.models.news_item import BROADCAST_FAILED, BROADCAST_NONE, BROADCAST_PENDING
from uk_management_bot.database.models.notice import (
    NOTICE_KIND_OUTAGE,
    NOTICE_SCOPE_ALL,
    NOTICE_STATUS_CLOSED,
    NOTICE_STATUS_DRAFT,
    NOTICE_STATUS_PUBLISHED,
    Notice,
)
from uk_management_bot.services.notices.audience import unknown_scope_ids
from uk_management_bot.utils.datetime_utils import utc_now

# Поля, которые менеджер задаёт сам (остальное — служебное).
EDITABLE_FIELDS = (
    "kind", "resource", "title_ru", "title_uz", "text_ru", "text_uz", "place_ru", "place_uz",
    "icon", "important", "publish_at", "starts_at", "ends_at", "all_day", "expires_at",
    "scope", "scope_ids",
)


class NoticeError(Exception):
    """Нарушение правил жизненного цикла (роутер отвечает 409/404)."""


class NoticeNotFound(NoticeError):
    pass


class NoticeInvalid(NoticeError):
    """Запись после правки противоречива (роутер отвечает 422)."""


def visible_clause(now: datetime):
    """Запись видна жителям в момент ``now``.

    Срок показа — ``expires_at``, а если он не задан, конец окна отключения:
    продлили отключение — показ продлился сам (хранить копию ``ends_at`` в
    ``expires_at`` нельзя, она отставала бы при правке окна).
    """
    shown_until = func.coalesce(Notice.expires_at, Notice.ends_at)
    return and_(
        Notice.status == NOTICE_STATUS_PUBLISHED,
        or_(Notice.publish_at.is_(None), Notice.publish_at <= now),
        or_(shown_until.is_(None), shown_until > now),
    )


def state_of(notice: Notice, now: Optional[datetime] = None) -> str:
    """Состояние для интерфейса: draft | scheduled | active | expired | closed."""
    now = now or utc_now()
    if notice.status != NOTICE_STATUS_PUBLISHED:
        return notice.status
    if notice.publish_at is not None and _aware(notice.publish_at) > now:
        return "scheduled"
    shown_until = notice.expires_at or notice.ends_at
    if shown_until is not None and _aware(shown_until) <= now:
        return "expired"
    return "active"


def _aware(value: datetime) -> datetime:
    # sqlite в тестах отдаёт наивные значения tz-колонок — трактуем как UTC.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


async def get_notice(db: AsyncSession, notice_id: int) -> Notice:
    notice = await db.get(Notice, notice_id)
    if notice is None:
        raise NoticeNotFound(f"запись {notice_id} не найдена")
    return notice


async def list_notices(
    db: AsyncSession,
    *,
    kind: Optional[str] = None,
    status: Optional[str] = None,
    period_from: Optional[datetime] = None,
    period_to: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Notice], int]:
    """Лента (свежие выше). ``period_*`` — записи, попадающие в окно календаря:
    по окну отключения, а без него — по моменту публикации/создания."""
    conditions = []
    if kind:
        conditions.append(Notice.kind == kind)
    if status:
        conditions.append(Notice.status == status)
    anchor_start = func.coalesce(Notice.starts_at, Notice.publish_at, Notice.created_at)
    anchor_end = func.coalesce(Notice.ends_at, Notice.starts_at, Notice.publish_at, Notice.created_at)
    if period_to is not None:
        conditions.append(anchor_start < period_to)
    if period_from is not None:
        # Отложенная публикация видна в календаре и в день публикации.
        conditions.append(or_(anchor_end >= period_from, Notice.publish_at >= period_from))
    total = (await db.execute(select(func.count()).select_from(Notice).where(*conditions))).scalar_one()
    rows = await db.execute(
        select(Notice).where(*conditions)
        .order_by(func.coalesce(Notice.publish_at, Notice.created_at).desc(), Notice.id.desc())
        .limit(limit).offset(offset)
    )
    return list(rows.scalars().all()), int(total)


def _check(notice: Notice) -> None:
    """Правила целой записи. PATCH меняет поля по одному, поэтому проверяется
    то, что получилось, а не тело запроса."""
    if notice.kind == NOTICE_KIND_OUTAGE:
        if not notice.resource:
            raise NoticeInvalid("для отключения укажите, что отключают")
        if notice.starts_at is None:
            raise NoticeInvalid("для отключения укажите начало")
    if notice.starts_at is not None and notice.ends_at is not None and _aware(notice.ends_at) < _aware(notice.starts_at):
        raise NoticeInvalid("окончание раньше начала")
    if notice.status == NOTICE_STATUS_PUBLISHED and not (notice.title_ru or "").strip():
        raise NoticeInvalid("заголовок на русском обязателен для публикации")
    if (notice.scope or NOTICE_SCOPE_ALL) == NOTICE_SCOPE_ALL:
        notice.scope_ids = []
    elif not notice.scope_ids:
        raise NoticeInvalid("выберите дворы или дома, которым адресована запись")


async def _check_scope(db: AsyncSession, notice: Notice) -> None:
    unknown = await unknown_scope_ids(db, notice.scope or NOTICE_SCOPE_ALL, list(notice.scope_ids or []))
    if unknown:
        raise NoticeInvalid(f"нет в справочнике адресов: {unknown}")


def _apply_broadcast(notice: Notice, wanted: Optional[bool]) -> None:
    """Включить или отменить рассылку в Telegram.

    Очередь возьмёт запись, когда жители её увидят (см. api/notices/broadcast):
    отложенная уходит в момент публикации. Уже начатую или завершённую рассылку
    флаг не трогает — повтор только через ``retry_broadcast``.
    """
    if wanted is True and notice.broadcast_status == BROADCAST_NONE:
        notice.broadcast_status = BROADCAST_PENDING
        notice.broadcast_attempts, notice.broadcast_cursor = 0, 0
        notice.broadcast_next_at, notice.broadcast_details = None, None
    elif wanted is False and notice.broadcast_status == BROADCAST_PENDING:
        notice.broadcast_status = BROADCAST_NONE


async def create_notice(db: AsyncSession, fields: dict, *, user_id: Optional[int], publish: bool,
                        broadcast: Optional[bool] = None) -> Notice:
    notice = Notice(**{k: v for k, v in fields.items() if k in EDITABLE_FIELDS}, created_by=user_id)
    notice.status = NOTICE_STATUS_DRAFT
    notice.broadcast_status = BROADCAST_NONE
    if publish:
        _publish(notice)
    _check(notice)
    await _check_scope(db, notice)
    _apply_broadcast(notice, broadcast)
    db.add(notice)
    await db.commit()
    await db.refresh(notice)
    return notice


async def update_notice(db: AsyncSession, notice_id: int, fields: dict,
                        broadcast: Optional[bool] = None) -> Notice:
    notice = await get_notice(db, notice_id)
    if notice.status == NOTICE_STATUS_CLOSED:
        raise NoticeError("закрытую запись изменить нельзя")
    for key, value in fields.items():
        if key in EDITABLE_FIELDS:
            setattr(notice, key, value)
    try:
        _check(notice)
        await _check_scope(db, notice)
    except NoticeInvalid:
        await db.rollback()
        raise
    _apply_broadcast(notice, broadcast)
    await db.commit()
    await db.refresh(notice)
    return notice


def _publish(notice: Notice) -> None:
    if not (notice.title_ru or "").strip():
        raise NoticeInvalid("заголовок на русском обязателен для публикации")
    notice.status = NOTICE_STATUS_PUBLISHED
    if notice.publish_at is None:
        notice.publish_at = utc_now()


async def publish_notice(db: AsyncSession, notice_id: int) -> Notice:
    notice = await get_notice(db, notice_id)
    if notice.status == NOTICE_STATUS_CLOSED:
        raise NoticeError("закрытую запись опубликовать нельзя")
    _publish(notice)
    await db.commit()
    await db.refresh(notice)
    return notice


async def close_notice(db: AsyncSession, notice_id: int, *, user_id: Optional[int]) -> Notice:
    """Снять с витрины: запись остаётся в ленте и календаре как закрытая."""
    notice = await get_notice(db, notice_id)
    if notice.status != NOTICE_STATUS_CLOSED:
        notice.status = NOTICE_STATUS_CLOSED
        notice.closed_at = utc_now()
        notice.closed_by = user_id
        await db.commit()
        await db.refresh(notice)
    return notice


async def delete_notice(db: AsyncSession, notice_id: int) -> None:
    """Удалить можно только черновик: опубликованное закрывают — история нужна."""
    notice = await get_notice(db, notice_id)
    if notice.status != NOTICE_STATUS_DRAFT:
        raise NoticeError("удалить можно только черновик; опубликованную запись закройте")
    await db.delete(notice)
    await db.commit()


async def retry_broadcast(db: AsyncSession, notice_id: int) -> Notice:
    """Повторить рассылку, исчерпавшую попытки: шлёт только недоставленным."""
    notice = await get_notice(db, notice_id)
    if notice.broadcast_status != BROADCAST_FAILED:
        raise NoticeError("повторить можно только неудавшуюся рассылку")
    notice.broadcast_status = BROADCAST_PENDING
    notice.broadcast_attempts, notice.broadcast_next_at = 0, None
    await db.commit()
    await db.refresh(notice)
    return notice
