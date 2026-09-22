"""Unit tests for middlewares/throttling.py."""
import time
from dataclasses import replace

import pytest
from unittest.mock import MagicMock

from uk_management_bot.middlewares.throttling import ThrottlingMiddleware, _EVICTION_THRESHOLD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _noop_handler(event, data):
    data["_called"] = True
    return "ok"


def _make_message(user_id: int = 1001):
    msg = MagicMock()
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.media_group_id = None
    return msg


def _make_album_part(user_id: int = 1001, media_group_id: str = "album-1"):
    msg = _make_message(user_id)
    msg.media_group_id = media_group_id
    return msg


# ---------------------------------------------------------------------------
# Tests: constructor
# ---------------------------------------------------------------------------

class TestThrottlingMiddlewareInit:
    def test_default_rate_limit(self):
        mw = ThrottlingMiddleware()
        assert mw.rate_limit == 0.5

    def test_custom_rate_limit(self):
        mw = ThrottlingMiddleware(rate_limit=2.0)
        assert mw.rate_limit == 2.0

    def test_internal_state_starts_empty(self):
        mw = ThrottlingMiddleware()
        assert mw._last_message == {}


# ---------------------------------------------------------------------------
# Tests: message passing and throttling
# ---------------------------------------------------------------------------

class TestThrottlingMiddlewareCall:
    @pytest.mark.asyncio
    async def test_first_message_always_passes(self):
        mw = ThrottlingMiddleware(rate_limit=10.0)
        msg = _make_message(1001)
        data = {}

        result = await mw(handler=_noop_handler, event=msg, data=data)

        assert result == "ok"
        assert data.get("_called") is True

    @pytest.mark.asyncio
    async def test_second_message_within_rate_limit_dropped(self):
        mw = ThrottlingMiddleware(rate_limit=10.0)
        msg = _make_message(1001)
        data1, data2 = {}, {}

        await mw(handler=_noop_handler, event=msg, data=data1)
        result = await mw(handler=_noop_handler, event=msg, data=data2)

        assert result is None
        assert data2.get("_called") is None

    @pytest.mark.asyncio
    async def test_message_passes_after_rate_limit_elapsed(self):
        mw = ThrottlingMiddleware(rate_limit=0.01)
        msg = _make_message(1001)

        await mw(handler=_noop_handler, event=msg, data={})

        # Wait more than the rate limit
        import asyncio
        await asyncio.sleep(0.05)

        data = {}
        result = await mw(handler=_noop_handler, event=msg, data=data)

        assert result == "ok"
        assert data.get("_called") is True

    @pytest.mark.asyncio
    async def test_different_users_are_independent(self):
        mw = ThrottlingMiddleware(rate_limit=10.0)
        msg1 = _make_message(1001)
        msg2 = _make_message(1002)
        data1, data2 = {}, {}

        await mw(handler=_noop_handler, event=msg1, data={})
        result1 = await mw(handler=_noop_handler, event=msg1, data=data1)
        result2 = await mw(handler=_noop_handler, event=msg2, data=data2)

        # msg1 second send is throttled, msg2 first send passes
        assert result1 is None
        assert result2 == "ok"

    @pytest.mark.asyncio
    async def test_timestamp_updated_on_pass(self):
        mw = ThrottlingMiddleware(rate_limit=0.5)
        msg = _make_message(1001)

        before = time.monotonic()
        await mw(handler=_noop_handler, event=msg, data={})
        after = time.monotonic()

        ts = mw._last_message[1001]
        assert before <= ts <= after

    @pytest.mark.asyncio
    async def test_no_from_user_uses_id_zero(self):
        """Message with no from_user should use user_id=0 and not crash."""
        mw = ThrottlingMiddleware(rate_limit=10.0)
        msg = MagicMock()
        msg.from_user = None
        msg.media_group_id = None

        data = {}
        result = await mw(handler=_noop_handler, event=msg, data=data)

        assert result == "ok"
        assert 0 in mw._last_message

    @pytest.mark.asyncio
    async def test_no_from_user_second_message_throttled(self):
        mw = ThrottlingMiddleware(rate_limit=10.0)
        msg = MagicMock()
        msg.from_user = None
        msg.media_group_id = None

        await mw(handler=_noop_handler, event=msg, data={})
        result = await mw(handler=_noop_handler, event=msg, data={})

        assert result is None


# ---------------------------------------------------------------------------
# Tests: albums (A9-P1-1)
# ---------------------------------------------------------------------------

class TestThrottlingAlbums:
    """Альбом = одно действие пользователя, которое Telegram присылает N
    апдейтами за миллисекунды. Троттлинг считает альбом одним сообщением:
    старт альбома подчиняется rate_limit, его части (≤10, в коротком окне)
    проходят. ``media_group_id`` задаёт клиент — полный пропуск снял бы
    антифлуд (юзербот шлёт альбомы в цикле)."""

    @staticmethod
    async def _send(mw, msgs):
        return [await mw(handler=_noop_handler, event=m, data={}) for m in msgs]

    @pytest.mark.asyncio
    async def test_all_parts_of_album_pass(self):
        mw = ThrottlingMiddleware(rate_limit=10.0)
        calls = []

        async def handler(event, data):
            calls.append(event)
            return "ok"

        album = [_make_album_part(1001) for _ in range(5)]
        results = [await mw(handler=handler, event=m, data={}) for m in album]

        assert results == ["ok"] * 5
        assert calls == album

    @pytest.mark.asyncio
    async def test_full_album_of_ten_passes(self):
        mw = ThrottlingMiddleware(rate_limit=10.0)
        results = await self._send(mw, [_make_album_part(1001) for _ in range(10)])
        assert results == ["ok"] * 10

    @pytest.mark.asyncio
    async def test_eleventh_part_of_same_album_dropped(self):
        mw = ThrottlingMiddleware(rate_limit=10.0)
        results = await self._send(mw, [_make_album_part(1001) for _ in range(11)])
        assert results == ["ok"] * 10 + [None]

    @pytest.mark.asyncio
    async def test_album_flood_only_first_album_passes(self):
        mw = ThrottlingMiddleware(rate_limit=10.0)
        msgs = [
            _make_album_part(1001, media_group_id=f"album-{a}")
            for a in range(3) for _ in range(4)
        ]
        results = await self._send(mw, msgs)
        assert results == ["ok"] * 4 + [None] * 8

    @staticmethod
    def _age(mw, user_id, seconds):
        """Сдвинуть в прошлое всё per-user состояние (без патча time.monotonic)."""
        mw._last_message[user_id] -= seconds
        album = mw._albums[user_id]
        mw._albums[user_id] = replace(album, started_at=album.started_at - seconds)

    @pytest.mark.asyncio
    async def test_second_album_soon_after_first_is_dropped(self):
        """Старт нового альбома — не чаще _ALBUM_START_INTERVAL (≥2 с), иначе
        худший случай 10 фото каждые rate_limit = 20 msg/s."""
        mw = ThrottlingMiddleware(rate_limit=0.5)
        first = await self._send(mw, [_make_album_part(1001, "a1") for _ in range(3)])
        self._age(mw, 1001, 0.6)
        second = await self._send(mw, [_make_album_part(1001, "a2") for _ in range(3)])

        assert first == ["ok"] * 3
        assert second == [None] * 3

    @pytest.mark.asyncio
    async def test_second_album_after_start_interval_passes(self):
        mw = ThrottlingMiddleware(rate_limit=0.5)
        await self._send(mw, [_make_album_part(1001, "a1") for _ in range(3)])
        self._age(mw, 1001, 2.1)
        second = await self._send(mw, [_make_album_part(1001, "a2") for _ in range(3)])

        assert second == ["ok"] * 3

    @pytest.mark.asyncio
    async def test_text_is_not_slowed_by_album_start_interval(self):
        """Обычные сообщения по-прежнему по rate_limit, а не по интервалу альбомов."""
        mw = ThrottlingMiddleware(rate_limit=0.5)
        await self._send(mw, [_make_album_part(1001, "a1") for _ in range(3)])
        self._age(mw, 1001, 0.6)

        result = await mw(handler=_noop_handler, event=_make_message(1001), data={})

        assert result == "ok"

    @pytest.mark.asyncio
    async def test_same_album_part_after_window_dropped(self):
        mw = ThrottlingMiddleware(rate_limit=10.0)
        await self._send(mw, [_make_album_part(1001) for _ in range(2)])
        # окно альбома давно истекло (и rate_limit тоже — не он режет)
        album = mw._albums[1001]
        mw._albums[1001] = replace(album, started_at=album.started_at - 100.0)
        mw._last_message[1001] -= 100.0

        result = await mw(handler=_noop_handler, event=_make_album_part(1001), data={})

        assert result is None

    @pytest.mark.asyncio
    async def test_album_right_after_text_is_throttled(self):
        mw = ThrottlingMiddleware(rate_limit=10.0)
        await mw(handler=_noop_handler, event=_make_message(1001), data={})

        results = await self._send(mw, [_make_album_part(1001) for _ in range(3)])

        assert results == [None] * 3

    @pytest.mark.asyncio
    async def test_text_right_after_album_is_throttled(self):
        mw = ThrottlingMiddleware(rate_limit=10.0)
        await self._send(mw, [_make_album_part(1001) for _ in range(3)])

        result = await mw(handler=_noop_handler, event=_make_message(1001), data={})

        assert result is None

    @pytest.mark.asyncio
    async def test_album_state_is_evicted_with_stale_users(self):
        mw = ThrottlingMiddleware(rate_limit=0.5)
        await mw(handler=_noop_handler, event=_make_album_part(1), data={})
        template = mw._albums[1]
        stale = time.monotonic() - 100.0
        for uid in range(_EVICTION_THRESHOLD + 1):
            mw._last_message[uid] = stale
            mw._albums[uid] = replace(template, started_at=stale)

        await mw(handler=_noop_handler, event=_make_album_part(10**9), data={})

        assert list(mw._albums) == [10**9]


# ---------------------------------------------------------------------------
# Tests: memory eviction
# ---------------------------------------------------------------------------

class TestThrottlingMiddlewareEviction:
    @pytest.mark.asyncio
    async def test_eviction_occurs_when_threshold_exceeded(self):
        mw = ThrottlingMiddleware(rate_limit=0.0)

        # Pre-populate with stale entries (way in the past)
        stale_time = time.monotonic() - 100.0
        for uid in range(_EVICTION_THRESHOLD):
            mw._last_message[uid] = stale_time

        # Add one more entry to trigger eviction logic
        extra_user_id = _EVICTION_THRESHOLD + 1
        msg = _make_message(extra_user_id)

        await mw(handler=_noop_handler, event=msg, data={})

        # All stale entries should have been evicted
        assert len(mw._last_message) < _EVICTION_THRESHOLD

    @pytest.mark.asyncio
    async def test_no_eviction_below_threshold(self):
        """If count <= threshold, no eviction happens."""
        mw = ThrottlingMiddleware(rate_limit=0.5)

        # Add fewer entries than the eviction threshold
        for uid in range(100):
            mw._last_message[uid] = time.monotonic() - 200.0

        initial_count = len(mw._last_message)
        msg = _make_message(9999)

        await mw(handler=_noop_handler, event=msg, data={})

        # No eviction should have happened (count was below threshold)
        assert len(mw._last_message) >= initial_count


# ---------------------------------------------------------------------------
# Tests: EVICTION_THRESHOLD constant
# ---------------------------------------------------------------------------

class TestEvictionThreshold:
    def test_threshold_is_positive_integer(self):
        assert isinstance(_EVICTION_THRESHOLD, int)
        assert _EVICTION_THRESHOLD > 0

    def test_threshold_is_reasonably_large(self):
        # Should be at least 1000 to make sense for production use
        assert _EVICTION_THRESHOLD >= 1000
