"""A11-CODE-02: лимитер LLM-вызовов news-watch.

Гарантии: (1) Redis недоступен → LLM не вызывается (fail-closed), новость
остаётся pending для человека; (2) повтор транзиентного сбоя тоже тратит
бюджет — при исчерпанном бюджете второго платного вызова нет; (3) счётчик
всегда с TTL (INCR и EXPIRE одной Lua-операцией, ключ без TTL получает срок);
(4) бюджет общий для всех воркеров API — глобальный ключ в Redis (в тесте —
два независимых подключения одного процесса к одному ключу).

Redis-тесты — на настоящем Redis (локальный uk-redis / сервис CI), без него skip.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
import redis.asyncio as aioredis
from sqlalchemy import select

from uk_management_bot.config.settings import settings
from uk_management_bot.database.models.news_item import NEWS_STATUS_PENDING, NewsItem
from uk_management_bot.services.group_intake import pending
from uk_management_bot.services.llm import client as llm
from uk_management_bot.services.news_watch import limiter, pipeline
from uk_management_bot.services.news_watch.config import DEFAULT_CONFIG, save_config
from uk_management_bot.services.news_watch.pipeline import Inbound

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)
TEXT = "Плановое отключение воды 07.11 с 10:00 до 16:00 по ул. Тестовая"


async def _redis_available() -> bool:
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=1)
    try:
        await r.ping()
        return True
    except Exception:
        return False
    finally:
        await r.aclose()


@pytest.fixture()
async def redis_client(monkeypatch):
    if not await _redis_available():
        if os.getenv("CI"):  # в CI Redis есть всегда: пропуск здесь = молча непроверенные гарантии
            pytest.fail("Redis недоступен в CI — тесты лимитера news-watch не должны пропускаться")
        pytest.skip("Redis недоступен — гарантии лимитера проверяются на настоящем Redis")
    # Свой ключ на тест: не трогать боевой nw:llm и не пересекаться с параллельными прогонами.
    monkeypatch.setattr(limiter, "KEY", f"nw:llm:test:{uuid.uuid4().hex}")
    await pending.aclose()
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    await r.delete(limiter.KEY)
    try:
        yield r
    finally:
        await r.delete(limiter.KEY)
        await r.aclose()
        await pending.aclose()


@pytest.fixture
async def ctx(el_async_factory, monkeypatch):
    monkeypatch.setattr(settings, "NEWS_WATCH_ENABLED", True)
    async with el_async_factory() as db:
        await save_config(db, {**DEFAULT_CONFIG, "complex_context": "ЖК Тест, ул. Тестовая"})
    return el_async_factory


async def _ingest(factory) -> NewsItem:
    async with factory() as db:
        item, created = await pipeline.ingest(db, Inbound(
            source_chat_id=-1001, source_message_id=1, chat_title="Водоканал", text=TEXT, posted_at=NOW))
        assert created
    async with factory() as db:
        return (await db.execute(select(NewsItem).where(NewsItem.id == item.id))).scalar_one()


class _BrokenRedis:
    async def eval(self, *args, **kwargs):
        raise ConnectionError("redis down")


# ───────────── fail-closed ─────────────


async def test_redis_down_means_not_allowed(monkeypatch):
    monkeypatch.setattr(pending, "_get_client", lambda: _BrokenRedis())
    assert await limiter.news_watch_llm_allowed() is False


async def test_redis_down_ingest_skips_llm_and_keeps_item_pending(ctx, monkeypatch):
    monkeypatch.setattr(pending, "_get_client", lambda: _BrokenRedis())
    llm_call = AsyncMock(return_value={"relevant": True})
    monkeypatch.setattr(pipeline, "llm_json_async", llm_call)
    item = await _ingest(ctx)
    llm_call.assert_not_awaited()
    assert item.status == NEWS_STATUS_PENDING and item.relevant is None


# ───────────── настоящий Redis ─────────────


async def test_counter_gets_ttl_on_first_call(redis_client):
    assert await limiter.news_watch_llm_allowed() is True
    ttl = await redis_client.ttl(limiter.KEY)
    assert 0 < ttl <= limiter.WINDOW_SECONDS


async def test_counter_without_ttl_gets_expiry(redis_client):
    await redis_client.set(limiter.KEY, "0")  # наследие сбоя: ключ без срока
    assert await redis_client.ttl(limiter.KEY) == -1
    await limiter.news_watch_llm_allowed()
    assert 0 < await redis_client.ttl(limiter.KEY) <= limiter.WINDOW_SECONDS


async def test_budget_is_shared_between_workers(redis_client, monkeypatch):
    """Два воркера API = два независимых подключения к одному ключу."""
    monkeypatch.setattr(settings, "NEWS_WATCH_LLM_PER_MINUTE", 3)
    worker_a = [await limiter.news_watch_llm_allowed() for _ in range(2)]
    await pending.aclose()  # следующий вызов — новое подключение («другой воркер»)
    worker_b = [await limiter.news_watch_llm_allowed() for _ in range(3)]
    assert worker_a + worker_b == [True, True, True, False, False]


async def test_exhausted_budget_blocks_paid_retry(ctx, redis_client, monkeypatch):
    """Бюджет 1: первый вызов разрешён, транзиентный сбой → повтор упирается в лимит."""
    monkeypatch.setattr(settings, "NEWS_WATCH_LLM_PER_MINUTE", 1)
    create = AsyncMock(side_effect=TimeoutError())
    monkeypatch.setattr(llm, "_get_async_client", lambda: type("C", (), {
        "messages": type("M", (), {"create": staticmethod(create)})()})())
    monkeypatch.setattr(llm, "_sleep", AsyncMock())
    item = await _ingest(ctx)
    assert create.await_count == 1  # второго платного вызова нет
    assert item.status == NEWS_STATUS_PENDING and item.relevant is None
