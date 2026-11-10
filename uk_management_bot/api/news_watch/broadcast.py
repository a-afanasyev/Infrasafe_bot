"""Воркер рассылки опубликованных новостей — outbox, а не fire-and-forget.

Живёт в ``api/`` (шлёт через httpx-sender API; домен ``services`` HTTP-пакет не
импортирует). Цикл (``api/lifecycle.py``, раз в 30 с): переставить застрявшие ``running``
(старше STALE) в ``failed`` с бэкоффом → взять ОДНУ новость ``pending|failed``
с ``next_at <= now`` и ``attempts < MAX`` → ``running`` → жители
(``users.id > cursor``, applicant, approved, не удалён, бот не заблокирован)
через httpx-sender API, курсор фиксируется после каждой отправки →
группы жителей. Любое исключение → ``failed``, ``attempts+1``,
``next_at = now + 2^attempts мин``, курсор сохранён — после рестарта
продолжение без дублей. 429: ждём ``retry_after`` и повторяем того же
получателя один раз.

A11-CODE-02: временная ошибка доставки (не blocked/no_chat) — житель в
``details.retry``, неудачная группа — в ``details.groups_failed``; ``done``
только если оба пусты, иначе ``failed`` с бэкоффом, и следующая попытка шлёт
сначала им. ABORT_AFTER_ERRORS ошибок подряд (нет связи с Telegram) — проход
прерывается, а не прожигает весь список.
"""
from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from uk_management_bot.api import telegram_send
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.monitored_group import GROUP_KIND_RESIDENTS, MonitoredGroup
from uk_management_bot.database.models.news_item import (
    BROADCAST_DONE,
    BROADCAST_FAILED,
    BROADCAST_PENDING,
    BROADCAST_RUNNING,
    NEWS_STATUS_PUBLISHED,
    NewsItem,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.database.roles_type import roles_contain
from uk_management_bot.services.news_watch.config import load_config
from uk_management_bot.utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
STALE = timedelta(minutes=10)
PAUSE_SECONDS = 0.05
# Курсор фиксируется после КАЖДОЙ отправки: один UPDATE на сообщение при
# паузе 50 мс — дёшево, зато рестарт воркера не даёт ни одного дубля.
BATCH = 200
ABORT_AFTER_ERRORS = 10
# Сон 429 без heartbeat: дольше STALE — второй воркер возьмёт рассылку и пошлёт дубли.
MAX_RETRY_AFTER_SECONDS = 60

Sender = Callable[..., Awaitable[telegram_send.TelegramResult]]


class TelegramUnavailable(Exception):
    """ABORT_AFTER_ERRORS ошибок подряд — связи с Telegram нет."""


def _backoff(attempts: int) -> timedelta:
    return timedelta(minutes=2 ** max(1, attempts))


def _render(item: NewsItem) -> str:
    from uk_management_bot.services.news_watch.pipeline import kind_title, strip_tags
    from uk_management_bot.utils.helpers import get_text

    # A11-CODE-01: summary (ответ LLM) и raw_text (текст чужого канала) — внешний
    # ввод → теги вырезаны + html.escape; разметка шаблона локали и kind_title — наши.
    parts = [
        get_text("news_watch.broadcast", language=lang, title=kind_title(item.kind, lang),
                 text=html.escape(strip_tags(
                     (item.summary_ru if lang == "ru" else item.summary_uz) or item.raw_text[:500])))
        for lang in ("ru", "uz")
    ]
    return "\n\n".join(parts)


async def _requeue_stale(db: AsyncSession, now: datetime) -> int:
    rows = (await db.execute(
        select(NewsItem).where(NewsItem.broadcast_status == BROADCAST_RUNNING,
                               NewsItem.broadcast_started_at < now - STALE)
    )).scalars().all()
    for item in rows:
        item.broadcast_status = BROADCAST_FAILED
        item.broadcast_attempts = (item.broadcast_attempts or 0) + 1
        item.broadcast_next_at = now + _backoff(item.broadcast_attempts)
        logger.warning("news_watch.broadcast: item %s stale running → failed (attempt %s)",
                       item.id, item.broadcast_attempts)
    if rows:
        await db.commit()
    return len(rows)


async def _claim(db: AsyncSession, now: datetime) -> Optional[int]:
    item = (await db.execute(
        select(NewsItem)
        .where(NewsItem.status == NEWS_STATUS_PUBLISHED,
               NewsItem.broadcast_status.in_((BROADCAST_PENDING, BROADCAST_FAILED)),
               NewsItem.broadcast_attempts < MAX_ATTEMPTS,
               or_(NewsItem.broadcast_next_at.is_(None), NewsItem.broadcast_next_at <= now))
        .order_by(NewsItem.id).limit(1)
        # API — несколько uvicorn-воркеров, цикл в каждом: без SKIP LOCKED два
        # воркера берут один pending и шлют дважды (как у webhook_sender).
        # sqlite (тесты) FOR UPDATE игнорирует — гарантия только на PostgreSQL.
        .with_for_update(skip_locked=True)
    )).scalar_one_or_none()
    if item is None:
        return None
    item.broadcast_status, item.broadcast_started_at = BROADCAST_RUNNING, now
    await db.commit()
    return item.id


def _eligible():
    return (roles_contain(User.roles, "applicant"), User.status == "approved",
            User.deleted_at.is_(None), User.bot_blocked_at.is_(None))


async def _recipients(db: AsyncSession, after_id: int) -> list[tuple[int, int]]:
    rows = await db.execute(
        select(User.id, User.telegram_id).where(User.id > after_id, *_eligible())
        .order_by(User.id).limit(BATCH)
    )
    return [(int(uid), int(tg)) for uid, tg in rows.all() if tg]


async def _retry_recipients(db: AsyncSession, user_ids: list[int]) -> list[tuple[int, int]]:
    """Жители из списка повтора, всё ещё подходящие (выбывшие — молча из списка)."""
    if not user_ids:
        return []
    rows = await db.execute(
        select(User.id, User.telegram_id).where(User.id.in_(user_ids), *_eligible()).order_by(User.id)
    )
    return [(int(uid), int(tg)) for uid, tg in rows.all() if tg]


async def _set(db: AsyncSession, item_id: int, **values) -> None:
    await db.execute(update(NewsItem).where(NewsItem.id == item_id).values(**values))
    await db.commit()


async def _progress(db: AsyncSession, item_id: int, **values) -> None:
    """Сдвиг курсора/счётчиков + heartbeat: ``broadcast_started_at`` = последний
    прогресс, иначе рассылка длиннее STALE выглядит «протухшей» для второго
    воркера и уходит жителям второй раз."""
    await _set(db, item_id, broadcast_started_at=utc_now(), **values)


async def _send_once(send: Sender, sleep, chat_id: int, text: str) -> telegram_send.TelegramResult:
    result = await send(chat_id, text, parse_mode="HTML")
    if result.retry_after is not None:
        await sleep(min(float(result.retry_after), MAX_RETRY_AFTER_SECONDS))
        result = await send(chat_id, text, parse_mode="HTML")
    return result


async def _deliver(factory, item_id: int, send: Sender, sleep) -> dict:
    async with factory() as db:
        item = await db.get(NewsItem, item_id)
        cfg = await load_config(db)
        text = _render(item)
        cursor = item.broadcast_cursor or 0
        details = dict(item.broadcast_details or {})
    counters = {key: int(details.get(key, 0)) for key in ("sent", "blocked", "no_chat")}
    retry: list[int] = [int(u) for u in details.get("retry", [])]
    groups_done: list[int] = list(details.get("groups", []))
    groups_failed: list[int] = []
    streak = 0  # ошибок подряд

    def snapshot() -> dict:
        # errors — недоставлено СЕЙЧАС (не число неудачных попыток за все проходы)
        return {**counters, "errors": len(retry) + len(groups_failed),
                "retry": list(retry), "groups": groups_done, "groups_failed": groups_failed}

    async def save(**values) -> None:
        async with factory() as db:
            await _progress(db, item_id, broadcast_details=snapshot(), **values)

    async def deliver_dm(uid: int, tg_id: int) -> None:
        nonlocal streak
        result = await _send_once(send, sleep, tg_id, text)
        if uid in retry:
            retry.remove(uid)
        if result.ok:
            counters["sent"] += 1
        elif result.status == telegram_send.STATUS_BLOCKED:
            counters["blocked"] += 1
        elif result.status == telegram_send.STATUS_NO_CHAT:
            counters["no_chat"] += 1  # не открывал чат с ботом — повтор не поможет
        else:
            retry.append(uid)
            streak += 1
            if streak >= ABORT_AFTER_ERRORS:
                # uid уже в retry: курсор за ним, иначе продолжение пошлёт ему дважды
                await save(broadcast_cursor=max(cursor, uid))
                raise TelegramUnavailable()
            return
        streak = 0

    if not cfg["broadcast"]["dm"]:
        retry.clear()  # личку выключили — повторять в неё больше некому
    else:
        async with factory() as db:
            pending_retry = await _retry_recipients(db, retry)
        still = {uid for uid, _ in pending_retry}
        retry[:] = [u for u in retry if u in still]
        for uid, tg_id in pending_retry:
            await deliver_dm(uid, tg_id)
            await save()
            await sleep(PAUSE_SECONDS)
        while True:
            async with factory() as db:
                batch = await _recipients(db, cursor)
            if not batch:
                break
            for uid, tg_id in batch:
                await deliver_dm(uid, tg_id)
                cursor = uid
                await save(broadcast_cursor=cursor)
                await sleep(PAUSE_SECONDS)

    if cfg["broadcast"]["residents_groups"]:
        async with factory() as db:
            chats = (await db.execute(
                select(MonitoredGroup.chat_id).where(MonitoredGroup.kind == GROUP_KIND_RESIDENTS,
                                                     MonitoredGroup.is_active.is_(True))
                .order_by(MonitoredGroup.id)
            )).scalars().all()
        for chat_id in chats:
            if int(chat_id) in groups_done:
                continue
            result = await _send_once(send, sleep, int(chat_id), text)
            if result.ok:
                groups_done.append(int(chat_id))
            else:
                groups_failed.append(int(chat_id))
            await save()
            await sleep(PAUSE_SECONDS)
    return snapshot()


async def run_broadcast_cycle(factory=None, *, send: Optional[Sender] = None,
                              sleep=asyncio.sleep, now: Optional[datetime] = None) -> dict:
    """Один цикл воркера. Не бросает. Возвращает счётчики для логов/тестов."""
    stats = {"processed": 0, "done": 0, "failed": 0, "requeued": 0}
    if not settings.NEWS_WATCH_ENABLED:
        return stats
    if factory is None:
        from uk_management_bot.database.session import AsyncSessionLocal
        factory = AsyncSessionLocal
        if factory is None:
            return stats
    send = send or telegram_send.send_message
    now = now or datetime.now(timezone.utc)

    async with factory() as db:
        stats["requeued"] = await _requeue_stale(db, now)
        item_id = await _claim(db, now)
    if item_id is None:
        return stats
    stats["processed"] = 1
    try:
        details = await _deliver(factory, item_id, send, sleep)
    except Exception as e:
        logger.warning("news_watch.broadcast: item %s failed: %s", item_id, type(e).__name__)
        async with factory() as db:
            item = await db.get(NewsItem, item_id)
            attempts = (item.broadcast_attempts or 0) + 1
            await _set(db, item_id, broadcast_status=BROADCAST_FAILED, broadcast_attempts=attempts,
                       broadcast_next_at=now + _backoff(attempts))
        stats["failed"] = 1
        return stats
    if details["retry"] or details["groups_failed"]:
        async with factory() as db:
            item = await db.get(NewsItem, item_id)
            attempts = (item.broadcast_attempts or 0) + 1
            await _set(db, item_id, broadcast_status=BROADCAST_FAILED, broadcast_details=details,
                       broadcast_attempts=attempts, broadcast_next_at=now + _backoff(attempts))
        logger.warning("news_watch.broadcast: item %s undelivered: %s residents, %s groups (attempt %s)",
                       item_id, len(details["retry"]), len(details["groups_failed"]), attempts)
        stats["failed"] = 1
        return stats
    async with factory() as db:
        await _set(db, item_id, broadcast_status=BROADCAST_DONE, broadcast_details=details,
                   broadcast_next_at=None)
    logger.info("news_watch.broadcast: item %s done: %s", item_id, details)
    stats["done"] = 1
    return stats


__all__ = ["run_broadcast_cycle", "MAX_ATTEMPTS", "STALE", "PAUSE_SECONDS"]
