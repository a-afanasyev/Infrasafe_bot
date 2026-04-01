"""Unit tests for middlewares/throttling.py."""
import time
import pytest
from unittest.mock import AsyncMock, MagicMock

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

        data = {}
        result = await mw(handler=_noop_handler, event=msg, data=data)

        assert result == "ok"
        assert 0 in mw._last_message

    @pytest.mark.asyncio
    async def test_no_from_user_second_message_throttled(self):
        mw = ThrottlingMiddleware(rate_limit=10.0)
        msg = MagicMock()
        msg.from_user = None

        await mw(handler=_noop_handler, event=msg, data={})
        result = await mw(handler=_noop_handler, event=msg, data={})

        assert result is None


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
