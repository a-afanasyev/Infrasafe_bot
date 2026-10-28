"""Воркер рассылки новостей (api/news_watch/broadcast.py): outbox-семантика.

Курсор по users.id — продолжение после падения без дублей; 429 — повтор того же
получателя после retry_after; 5 неудачных попыток → failed; «running» старше
10 мин — считается упавшим и переставляется в очередь с бэкоффом.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from uk_management_bot.api.telegram_send import STATUS_BLOCKED, STATUS_ERROR, STATUS_OK, TelegramResult
from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.monitored_group import MonitoredGroup
from uk_management_bot.database.models.news_item import (
    BROADCAST_DONE,
    BROADCAST_FAILED,
    BROADCAST_PENDING,
    BROADCAST_RUNNING,
    NEWS_STATUS_PUBLISHED,
    NewsItem,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.api.news_watch import broadcast
from uk_management_bot.services.news_watch.config import DEFAULT_CONFIG, save_config

NOW = datetime(2026, 10, 28, 9, 0, tzinfo=timezone.utc)
RESIDENTS = [(10 + i, 1000 + i) for i in range(45)]  # (user.id, telegram_id)
GROUP = -100555


@pytest.fixture
async def ctx(el_async_factory, monkeypatch):
    monkeypatch.setattr(settings, "NEWS_WATCH_ENABLED", True)
    monkeypatch.setattr(broadcast, "PAUSE_SECONDS", 0)
    async with el_async_factory() as db:
        db.add_all([User(id=uid, telegram_id=tg, roles='["applicant"]', active_role="applicant",
                         status="approved", language="ru") for uid, tg in RESIDENTS])
        db.add(User(id=3, telegram_id=30, roles='["manager"]', active_role="manager", status="approved"))
        db.add(User(id=4, telegram_id=40, roles='["applicant"]', status="approved",
                    bot_blocked_at=NOW))                                   # заблокировал бота
        db.add(User(id=5, telegram_id=50, roles='["applicant"]', status="pending"))  # не одобрен
        db.add(MonitoredGroup(chat_id=GROUP, title="дом", kind="residents", is_active=True))
        db.add(MonitoredGroup(chat_id=-100999, title="staff", kind="staff", is_active=True))
        await db.commit()
        await save_config(db, DEFAULT_CONFIG)
    return el_async_factory


async def _item(factory, **over) -> int:
    async with factory() as db:
        item = NewsItem(source_chat_id=-1, source_message_id=over.pop("msg", 1), raw_text="raw",
                        kind="power", summary_ru="нет света", summary_uz="chiroq yo'q",
                        status=NEWS_STATUS_PUBLISHED, published_at=NOW,
                        broadcast_status=over.pop("bs", BROADCAST_PENDING), **over)
        db.add(item)
        await db.commit()
        return item.id


async def _row(factory, item_id) -> NewsItem:
    async with factory() as db:
        return (await db.execute(select(NewsItem).where(NewsItem.id == item_id))).scalar_one()


class Sender:
    """Запоминает отправки; сценарии по chat_id."""

    def __init__(self, fail_for=(), retry_after_once=(), crash_at=None):
        self.sent: list[int] = []
        self.fail_for = set(fail_for)
        self.retry_once = set(retry_after_once)
        self.crash_at = crash_at

    async def __call__(self, chat_id, text, **kw):
        if self.crash_at is not None and len(self.sent) >= self.crash_at:
            raise RuntimeError("api died")
        if chat_id in self.retry_once:
            self.retry_once.discard(chat_id)
            return TelegramResult(STATUS_ERROR, 429, "Too Many Requests", retry_after=1.5)
        self.sent.append(chat_id)
        if chat_id in self.fail_for:
            return TelegramResult(STATUS_BLOCKED, 403, "blocked")
        return TelegramResult(STATUS_OK, 200)


async def _run(factory, sender, now=NOW):
    slept = []

    async def sleep(s):
        slept.append(s)

    result = await broadcast.run_broadcast_cycle(factory, send=sender, sleep=sleep, now=now)
    return result, slept


@pytest.mark.asyncio
async def test_sends_to_eligible_residents_and_groups_then_done(ctx):
    factory = ctx
    item_id = await _item(factory)
    sender = Sender()
    result, _ = await _run(factory, sender)
    assert result["processed"] == 1
    tgs = [tg for _, tg in RESIDENTS]
    assert sender.sent[: len(tgs)] == tgs           # по возрастанию users.id
    assert GROUP in sender.sent and -100999 not in sender.sent
    assert 40 not in sender.sent and 50 not in sender.sent and 30 not in sender.sent
    row = await _row(factory, item_id)
    assert row.broadcast_status == BROADCAST_DONE
    assert row.broadcast_details["sent"] == len(tgs) and row.broadcast_details["groups"] == [GROUP]
    # второй цикл — нечего делать
    result, _ = await _run(factory, Sender())
    assert result["processed"] == 0


@pytest.mark.asyncio
async def test_429_waits_retry_after_and_resends_same_recipient(ctx):
    factory = ctx
    await _item(factory)
    target = RESIDENTS[3][1]
    sender = Sender(retry_after_once=(target,))
    _, slept = await _run(factory, sender)
    assert 1.5 in slept
    assert sender.sent.count(target) == 1 and sender.sent.index(target) == 3


@pytest.mark.asyncio
async def test_crash_mid_way_then_resume_from_cursor_without_duplicates(ctx):
    factory = ctx
    item_id = await _item(factory)
    first = Sender(crash_at=25)
    result, _ = await _run(factory, first)
    row = await _row(factory, item_id)
    assert row.broadcast_status == BROADCAST_FAILED and row.broadcast_attempts == 1
    assert row.broadcast_next_at is not None and row.broadcast_cursor >= RESIDENTS[19][0]
    assert result["failed"] == 1

    second = Sender()
    _, _ = await _run(factory, second, now=NOW + timedelta(hours=1))
    assert set(first.sent) & set(second.sent) == set(), "повторов после рестарта нет"
    assert len(first.sent) + len(second.sent) >= len(RESIDENTS)
    assert (await _row(factory, item_id)).broadcast_status == BROADCAST_DONE


@pytest.mark.asyncio
async def test_backoff_respected_and_max_attempts(ctx):
    factory = ctx
    item_id = await _item(factory, broadcast_attempts=4, broadcast_next_at=NOW + timedelta(minutes=30))
    result, _ = await _run(factory, Sender())
    assert result["processed"] == 0  # next_at в будущем
    async with factory() as db:
        row = await db.get(NewsItem, item_id)
        row.broadcast_next_at = NOW - timedelta(minutes=1)
        await db.commit()
    result, _ = await _run(factory, Sender(crash_at=0))
    row = await _row(factory, item_id)
    assert row.broadcast_status == BROADCAST_FAILED and row.broadcast_attempts == 5
    result, _ = await _run(factory, Sender(), now=NOW + timedelta(days=1))
    assert result["processed"] == 0, "после 5 попыток воркер не берёт"


@pytest.mark.asyncio
async def test_stale_running_is_requeued_with_backoff(ctx):
    factory = ctx
    item_id = await _item(factory, bs=BROADCAST_RUNNING, broadcast_started_at=NOW - timedelta(minutes=30),
                          broadcast_cursor=RESIDENTS[9][0])
    result, _ = await _run(factory, Sender())
    row = await _row(factory, item_id)
    # застрявший running → failed с бэкоффом, в этом же цикле не берётся
    assert row.broadcast_status == BROADCAST_FAILED and row.broadcast_attempts == 1
    assert row.broadcast_next_at.replace(tzinfo=timezone.utc) > NOW and result["processed"] == 0
    sender = Sender()
    await _run(factory, sender, now=NOW + timedelta(hours=1))
    assert sender.sent[0] == RESIDENTS[10][1], "продолжение с курсора"


@pytest.mark.asyncio
async def test_blocked_counted_not_fatal(ctx):
    factory = ctx
    item_id = await _item(factory)
    sender = Sender(fail_for=(RESIDENTS[0][1], RESIDENTS[1][1]))
    await _run(factory, sender)
    row = await _row(factory, item_id)
    assert row.broadcast_status == BROADCAST_DONE
    assert row.broadcast_details["blocked"] == 2 and row.broadcast_details["sent"] == len(RESIDENTS) - 2


@pytest.mark.asyncio
async def test_channels_from_config(ctx):
    factory = ctx
    async with factory() as db:
        await save_config(db, {**DEFAULT_CONFIG, "broadcast": {"dm": False, "residents_groups": True}})
    await _item(factory)
    sender = Sender()
    await _run(factory, sender)
    assert sender.sent == [GROUP]


@pytest.mark.asyncio
async def test_flag_off_does_nothing(ctx, monkeypatch):
    factory = ctx
    await _item(factory)
    monkeypatch.setattr(settings, "NEWS_WATCH_ENABLED", False)
    sender = Sender()
    result, _ = await _run(factory, sender)
    assert result["processed"] == 0 and sender.sent == []
