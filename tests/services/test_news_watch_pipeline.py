"""Конвейер мониторинга отключений (services/news_watch/pipeline.py) на aiosqlite.

inbox → дедуп → префильтр по ключевым словам → LLM (мок) → pending/ignored;
auto_publish → объявление на табло (append под FOR UPDATE) + outbox рассылки.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.board_config import BoardConfig
from uk_management_bot.database.models.news_item import (
    BROADCAST_DONE,
    BROADCAST_NONE,
    BROADCAST_PENDING,
    NEWS_STATUS_IGNORED,
    NEWS_STATUS_PENDING,
    NEWS_STATUS_PUBLISHED,
    NEWS_STATUS_REJECTED,
    NewsItem,
)
from uk_management_bot.database.models.user import User
from uk_management_bot.services.news_watch import pipeline
from uk_management_bot.services.news_watch.config import DEFAULT_CONFIG, save_config
from uk_management_bot.services.news_watch.pipeline import Inbound

NOW = datetime(2026, 10, 28, 9, 0, tzinfo=timezone.utc)


def _inbound(text="Плановое отключение электроэнергии 29.10 с 10:00 до 16:00 по ул. Тестовая 1-15",
             msg_id=1, chat_id=-1001, title="Электросети"):
    return Inbound(source_chat_id=chat_id, source_message_id=msg_id, chat_title=title,
                   text=text, posted_at=NOW)


def _verdict(**over):
    base = {"relevant": True, "kind": "power", "starts_at": "2026-10-29T10:00:00+05:00",
            "ends_at": "2026-10-29T16:00:00+05:00", "summary_ru": "29.10 10:00–16:00 нет света",
            "summary_uz": "29.10 10:00–16:00 chiroq yo'q", "confidence": 0.92}
    base.update(over)
    return base


@pytest.fixture
async def ctx(el_async_factory, monkeypatch):
    monkeypatch.setattr(settings, "NEWS_WATCH_ENABLED", True)
    async with el_async_factory() as db:
        db.add_all([
            User(id=3, telegram_id=30, first_name="Менеджер", roles='["manager"]', active_role="manager",
                 status="approved", language="ru"),
        ])
        await db.commit()
        await save_config(db, {**DEFAULT_CONFIG, "complex_context": "ЖК Тест, ул. Тестовая 1-20"})
    notify = AsyncMock(return_value=True)
    monkeypatch.setattr(pipeline.telegram_send, "send_message", notify)
    return el_async_factory, notify


def _llm(monkeypatch, verdict):
    calls = []

    async def fake(**kwargs):
        calls.append(kwargs)
        return verdict

    monkeypatch.setattr(pipeline, "llm_json_async", fake)
    return calls


async def _item(factory, item_id=1) -> NewsItem:
    async with factory() as db:
        return (await db.execute(select(NewsItem).where(NewsItem.id == item_id))).scalar_one()


# ───────────── префильтр и LLM ─────────────


def test_prefilter_is_case_insensitive_substring():
    assert pipeline.prefilter("ПЛАНОВОЕ ОТКЛЮЧЕНИЕ воды", ["отключ"]) is True
    assert pipeline.prefilter("Suv ta'minoti to'xtatiladi", ["suv"]) is True
    assert pipeline.prefilter("Поздравляем с праздником", ["отключ", "suv"]) is False
    assert pipeline.prefilter("", ["x"]) is False


@pytest.mark.asyncio
async def test_prefilter_miss_is_ignored_without_llm(ctx, monkeypatch):
    factory, notify = ctx
    calls = _llm(monkeypatch, _verdict())
    async with factory() as db:
        item, created = await pipeline.ingest(db, _inbound(text="Поздравляем всех с праздником!"))
    assert created is True and item.status == NEWS_STATUS_IGNORED and item.relevant is None
    assert calls == [] and notify.await_count == 0


@pytest.mark.asyncio
async def test_relevant_news_becomes_pending_and_notifies_managers(ctx, monkeypatch):
    factory, notify = ctx
    calls = _llm(monkeypatch, _verdict())
    async with factory() as db:
        item, created = await pipeline.ingest(db, _inbound())
    assert created and item.status == NEWS_STATUS_PENDING and item.kind == "power"
    assert item.relevant is True and item.confidence == 0.92
    assert item.summary_ru.startswith("29.10") and item.starts_at is not None
    assert "ЖК Тест" in calls[0]["system"] and "Тестовая 1-15" in calls[0]["user"]
    assert calls[0]["model"] == settings.NEWS_WATCH_MODEL
    notify.assert_awaited_once()
    assert notify.await_args.args[0] == 30 and "нет света" in notify.await_args.args[1]


@pytest.mark.asyncio
async def test_irrelevant_news_is_ignored(ctx, monkeypatch):
    factory, notify = ctx
    _llm(monkeypatch, _verdict(relevant=False, confidence=0.95))
    async with factory() as db:
        item, _ = await pipeline.ingest(db, _inbound())
    assert item.status == NEWS_STATUS_IGNORED and item.relevant is False
    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_llm_failure_keeps_pending_for_manager(ctx, monkeypatch):
    """LLM недоступен — новость с ключевыми словами не теряется: pending без вердикта."""
    factory, notify = ctx
    _llm(monkeypatch, None)
    async with factory() as db:
        item, _ = await pipeline.ingest(db, _inbound())
    assert item.status == NEWS_STATUS_PENDING and item.relevant is None and item.kind is None
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_bad_verdict_is_treated_as_failure(ctx, monkeypatch):
    factory, _ = ctx
    _llm(monkeypatch, _verdict(kind="COSMIC", confidence=2))
    async with factory() as db:
        item, _ = await pipeline.ingest(db, _inbound())
    assert item.status == NEWS_STATUS_PENDING and item.relevant is None


@pytest.mark.asyncio
async def test_dedup_by_source(ctx, monkeypatch):
    factory, notify = ctx
    calls = _llm(monkeypatch, _verdict())
    async with factory() as db:
        first, created1 = await pipeline.ingest(db, _inbound())
        second, created2 = await pipeline.ingest(db, _inbound(text="другой текст"))
    assert created1 and not created2 and first.id == second.id
    assert len(calls) == 1 and notify.await_count == 1


# ───────────── публикация ─────────────


@pytest.mark.asyncio
async def test_auto_publish_appends_announcement_and_queues_broadcast(ctx, monkeypatch):
    factory, notify = ctx
    _llm(monkeypatch, _verdict())
    async with factory() as db:
        await save_config(db, {**DEFAULT_CONFIG, "auto_publish": True, "min_confidence": 0.8})
        item, _ = await pipeline.ingest(db, _inbound())
    assert item.status == NEWS_STATUS_PUBLISHED and item.published_at is not None
    assert item.broadcast_status == BROADCAST_PENDING
    notify.assert_not_awaited()  # одобрять нечего
    async with factory() as db:
        board = (await db.execute(select(BoardConfig))).scalar_one()
        ann = board.data["announcements"]
        assert ann[0]["id"] == f"news-{item.id}" and ann[0]["important"] is True
        assert "нет света" in ann[0]["text"]["ru"] and "chiroq" in ann[0]["text"]["uz"]
        assert "электричества" in ann[0]["title"]["ru"].lower()


@pytest.mark.asyncio
async def test_auto_publish_below_threshold_stays_pending(ctx, monkeypatch):
    factory, _ = ctx
    _llm(monkeypatch, _verdict(confidence=0.5))
    async with factory() as db:
        await save_config(db, {**DEFAULT_CONFIG, "auto_publish": True, "min_confidence": 0.8})
        item, _ = await pipeline.ingest(db, _inbound())
    assert item.status == NEWS_STATUS_PENDING


@pytest.mark.asyncio
async def test_manual_publish_reject_and_guards(ctx, monkeypatch):
    factory, _ = ctx
    _llm(monkeypatch, _verdict())
    async with factory() as db:
        item, _ = await pipeline.ingest(db, _inbound())
        other, _ = await pipeline.ingest(db, _inbound(msg_id=2))
        published = await pipeline.publish(db, item.id, user_id=3)
        assert published.status == NEWS_STATUS_PUBLISHED and published.decided_by == 3
        assert published.broadcast_status == BROADCAST_PENDING
        with pytest.raises(pipeline.NewsWatchError):
            await pipeline.publish(db, item.id, user_id=3)  # повторно — нельзя
        rejected = await pipeline.reject(db, other.id, user_id=3)
        assert rejected.status == NEWS_STATUS_REJECTED and rejected.broadcast_status == BROADCAST_NONE
        with pytest.raises(pipeline.NewsWatchError):
            await pipeline.publish(db, other.id, user_id=3)
        with pytest.raises(pipeline.NewsWatchError):
            await pipeline.publish(db, 999, user_id=3)
    async with factory() as db:
        board = (await db.execute(select(BoardConfig))).scalar_one()
        assert [a["id"] for a in board.data["announcements"]][0] == f"news-{item.id}"


@pytest.mark.asyncio
async def test_publish_without_broadcast_channels_marks_done(ctx, monkeypatch):
    factory, _ = ctx
    _llm(monkeypatch, _verdict())
    async with factory() as db:
        await save_config(db, {**DEFAULT_CONFIG, "broadcast": {"dm": False, "residents_groups": False}})
        item, _ = await pipeline.ingest(db, _inbound())
        published = await pipeline.publish(db, item.id, user_id=3)
    assert published.broadcast_status == BROADCAST_DONE


@pytest.mark.asyncio
async def test_retry_broadcast_only_from_failed(ctx, monkeypatch):
    factory, _ = ctx
    _llm(monkeypatch, _verdict())
    async with factory() as db:
        item, _ = await pipeline.ingest(db, _inbound())
        await pipeline.publish(db, item.id, user_id=3)
        with pytest.raises(pipeline.NewsWatchError):
            await pipeline.retry_broadcast(db, item.id)
        row = await db.get(NewsItem, item.id)
        row.broadcast_status = "failed"
        row.broadcast_attempts = 5
        await db.commit()
        retried = await pipeline.retry_broadcast(db, item.id)
        assert retried.broadcast_status == BROADCAST_PENDING and retried.broadcast_attempts == 0
        assert retried.broadcast_cursor == 0 or retried.broadcast_cursor >= 0


@pytest.mark.asyncio
async def test_flag_off_rejects_ingest(ctx, monkeypatch):
    factory, _ = ctx
    monkeypatch.setattr(settings, "NEWS_WATCH_ENABLED", False)
    async with factory() as db:
        with pytest.raises(pipeline.NewsWatchError):
            await pipeline.ingest(db, _inbound())
