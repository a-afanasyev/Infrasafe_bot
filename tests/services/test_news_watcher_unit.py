"""Юзербот мониторинга (news_watcher/watcher.py) без Telethon и сети."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from news_watcher.watcher import (
    ApiClient,
    Offsets,
    Settings,
    diff_sources,
    handle_message,
    inbound_payload,
    normalize_handle,
)

ENV = {"NEWS_WATCH_API_URL": "http://api:8000/", "NEWS_WATCH_SERVICE_TOKEN": "t",
       "TG_API_ID": "123", "TG_API_HASH": "h", "NEWS_WATCH_TG_SESSION": "s"}


def test_settings_from_env_requires_all_secrets():
    s = Settings.from_env(ENV)
    assert s.api_url == "http://api:8000" and s.api_id == 123 and s.refresh_seconds == 300
    with pytest.raises(RuntimeError):
        Settings.from_env({**ENV, "NEWS_WATCH_SERVICE_TOKEN": ""})


def test_diff_sources():
    assert diff_sources({"@a", "@b"}, {"@b", "@c"}) == ({"@c"}, {"@a"})
    assert normalize_handle("Toshkent_Elektr") == "@toshkent_elektr" and normalize_handle(None) is None


def test_offsets_persist_and_only_grow(tmp_path):
    path = tmp_path / "offsets.json"
    o = Offsets(str(path))
    assert o.is_new(-1, 5)
    o.mark(-1, 5)
    o.mark(-1, 3)  # назад не двигается
    assert not o.is_new(-1, 5) and o.is_new(-1, 6)
    assert Offsets(str(path)).is_new(-1, 5) is False
    assert Offsets(str(tmp_path / "missing.json")).is_new(-1, 1)


def _api(handler, sleeps):
    async def sleep(s):
        sleeps.append(s)

    transport = httpx.MockTransport(handler)
    return ApiClient(Settings.from_env(ENV), client=httpx.AsyncClient(transport=transport), sleep=sleep)


@pytest.mark.asyncio
async def test_fetch_sources_and_post_with_retry_on_5xx():
    calls = {"inbox": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Service-Token"] == "t"
        if request.url.path.endswith("/sources"):
            return httpx.Response(200, json={"sources": [{"chat": "@a", "title": ""}, {"nochat": 1}]})
        calls["inbox"] += 1
        if calls["inbox"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"id": 1, "status": "pending", "created": True})

    sleeps = []
    api = _api(handler, sleeps)
    assert await api.fetch_sources() == ["@a"]
    assert await api.post_inbox({"x": 1}) is True
    assert calls["inbox"] == 3 and sleeps == [2.0, 4.0]


@pytest.mark.asyncio
async def test_post_does_not_retry_4xx():
    seen = []

    def handler(request):
        seen.append(1)
        return httpx.Response(422)

    sleeps = []
    api = _api(handler, sleeps)
    assert await api.post_inbox({}) is False and len(seen) == 1 and sleeps == []


@pytest.mark.asyncio
async def test_post_retries_429_then_gives_up():
    seen = []

    def handler(request):
        seen.append(1)
        return httpx.Response(429)

    sleeps = []
    api = _api(handler, sleeps)
    assert await api.post_inbox({}) is False
    assert len(seen) == 4 and len(sleeps) == 3


@pytest.mark.asyncio
async def test_handle_message_marks_offset_only_when_accepted(tmp_path):
    results = iter([httpx.Response(500), httpx.Response(500), httpx.Response(500), httpx.Response(500),
                    httpx.Response(200, json={})])

    def handler(request):
        return next(results)

    api = _api(handler, [])
    offsets = Offsets(str(tmp_path / "o.json"))
    posted = datetime(2026, 10, 28, 9, 0, tzinfo=timezone.utc)
    assert await handle_message(api, offsets, chat_id=-1, message_id=10, chat_title="t",
                                text="отключение", posted_at=posted) is False
    assert offsets.is_new(-1, 10)
    assert await handle_message(api, offsets, chat_id=-1, message_id=10, chat_title="t",
                                text="отключение", posted_at=posted) is True
    assert not offsets.is_new(-1, 10)
    # пустой текст и старые id — пропуск без сети
    assert await handle_message(api, offsets, chat_id=-1, message_id=11, chat_title="t",
                                text="   ", posted_at=None) is False
    assert await handle_message(api, offsets, chat_id=-1, message_id=9, chat_title="t",
                                text="x", posted_at=None) is False


def test_inbound_payload_shape():
    p = inbound_payload(-1, 2, "x" * 300, "t" * 30000, datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert len(p["chat_title"]) == 255 and len(p["text"]) == 20000
    assert p["posted_at"].startswith("2026-01-01") and p["source_chat_id"] == -1
