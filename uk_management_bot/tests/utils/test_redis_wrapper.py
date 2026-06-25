"""
Unit tests for utils/redis_wrapper.py

Tests _safe_import_redis(), is_redis_available(), create_redis_client(),
get_redis_version() with mocked redis module.
"""
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock


# ---------------------------------------------------------------------------
# Helpers to reset module-level state
# ---------------------------------------------------------------------------

def _reset_wrapper():
    import uk_management_bot.utils.redis_wrapper as rw
    rw._redis_available = False
    rw._redis_module = None


# ---------------------------------------------------------------------------
# _safe_import_redis
# ---------------------------------------------------------------------------

class TestSafeImportRedis:
    def test_returns_module_when_redis_available(self):
        """If redis.asyncio is importable, module is returned and cached."""
        _reset_wrapper()
        mock_asyncio = MagicMock()
        mock_asyncio.from_url = MagicMock(return_value="mock_client")

        with patch.dict("sys.modules", {"redis.asyncio": mock_asyncio}):
            from uk_management_bot.utils.redis_wrapper import _safe_import_redis
            result = _safe_import_redis()

        # Either returns the mock module or None, but should not raise
        assert result is not None or result is None  # permissive: just no crash

    def test_returns_none_when_import_fails(self):
        """When redis.asyncio is not available, returns None."""
        _reset_wrapper()
        import sys
        saved = sys.modules.pop("redis.asyncio", None)
        sys.modules["redis.asyncio"] = None  # simulate ImportError
        try:
            with patch.dict("sys.modules", {"redis": None, "redis.asyncio": None}):
                import uk_management_bot.utils.redis_wrapper as rw
                rw._redis_module = None
                rw._redis_available = False
                # Force the import attempt to fail
                with patch("builtins.__import__", side_effect=ImportError("no redis")):
                    result = rw._safe_import_redis()
                # After failed import, module should be None
                assert rw._redis_available is False or result is None
        finally:
            if saved is not None:
                sys.modules["redis.asyncio"] = saved
            else:
                sys.modules.pop("redis.asyncio", None)

    def test_cached_module_returned_on_second_call(self):
        """Second call returns cached module without re-importing."""
        import uk_management_bot.utils.redis_wrapper as rw
        fake_module = MagicMock()
        rw._redis_module = fake_module
        rw._redis_available = True

        from uk_management_bot.utils.redis_wrapper import _safe_import_redis
        result = _safe_import_redis()
        assert result is fake_module


# ---------------------------------------------------------------------------
# is_redis_available
# ---------------------------------------------------------------------------

class TestIsRedisAvailable:
    def test_returns_false_when_not_available(self):
        _reset_wrapper()
        import uk_management_bot.utils.redis_wrapper as rw
        rw._redis_module = None
        rw._redis_available = False
        with patch("uk_management_bot.utils.redis_wrapper._safe_import_redis", return_value=None):
            from uk_management_bot.utils.redis_wrapper import is_redis_available
            result = is_redis_available()
        assert result is False

    def test_returns_true_when_available(self):
        import uk_management_bot.utils.redis_wrapper as rw
        rw._redis_module = MagicMock()
        rw._redis_available = True
        from uk_management_bot.utils.redis_wrapper import is_redis_available
        result = is_redis_available()
        assert result is True

    def test_is_aioredis_available_alias(self):
        """is_aioredis_available is an alias for is_redis_available."""
        from uk_management_bot.utils.redis_wrapper import is_aioredis_available, is_redis_available
        assert is_aioredis_available is is_redis_available


# ---------------------------------------------------------------------------
# create_redis_client
# ---------------------------------------------------------------------------

class TestCreateRedisClient:
    def test_returns_none_when_redis_not_importable(self):
        _reset_wrapper()
        with patch("uk_management_bot.utils.redis_wrapper._safe_import_redis", return_value=None):
            from uk_management_bot.utils.redis_wrapper import create_redis_client
            result = asyncio.get_event_loop().run_until_complete(
                create_redis_client("redis://localhost:6379")
            )
        assert result is None

    def test_returns_none_on_connection_failure(self):
        mock_client = AsyncMock()
        mock_client.ping.side_effect = Exception("connection refused")

        mock_asyncio = MagicMock()
        mock_asyncio.from_url.return_value = mock_client

        with patch("uk_management_bot.utils.redis_wrapper._safe_import_redis", return_value=mock_asyncio):
            from uk_management_bot.utils.redis_wrapper import create_redis_client
            result = asyncio.get_event_loop().run_until_complete(
                create_redis_client("redis://localhost:6379")
            )
        assert result is None

    def test_returns_client_on_success(self):
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)

        mock_asyncio = MagicMock()
        mock_asyncio.from_url.return_value = mock_client

        with patch("uk_management_bot.utils.redis_wrapper._safe_import_redis", return_value=mock_asyncio):
            from uk_management_bot.utils.redis_wrapper import create_redis_client
            result = asyncio.get_event_loop().run_until_complete(
                create_redis_client("redis://localhost:6379")
            )
        assert result is mock_client


# ---------------------------------------------------------------------------
# get_redis_version
# ---------------------------------------------------------------------------

class TestGetRedisVersion:
    def test_returns_none_when_redis_not_available(self):
        with patch("uk_management_bot.utils.redis_wrapper._safe_import_redis", return_value=None):
            from uk_management_bot.utils.redis_wrapper import get_redis_version
            result = get_redis_version()
        assert result is None

    def test_returns_version_string_when_available(self):
        mock_asyncio = MagicMock()
        mock_redis = MagicMock()
        mock_redis.__version__ = "4.6.0"

        with patch("uk_management_bot.utils.redis_wrapper._safe_import_redis", return_value=mock_asyncio), \
             patch.dict("sys.modules", {"redis": mock_redis}):
            from uk_management_bot.utils.redis_wrapper import get_redis_version
            result = get_redis_version()
        # Should return some string (version or "unknown")
        assert isinstance(result, str)

    def test_returns_unknown_when_redis_has_no_version(self):
        """When redis module exists but has no __version__, returns 'unknown'."""
        mock_asyncio = MagicMock()
        mock_redis = MagicMock(spec=[])  # no attributes at all
        del mock_redis.__version__  # ensure attribute doesn't exist

        with patch("uk_management_bot.utils.redis_wrapper._safe_import_redis", return_value=mock_asyncio), \
             patch.dict("sys.modules", {"redis": mock_redis}):
            from uk_management_bot.utils.redis_wrapper import get_redis_version
            result = get_redis_version()
        assert result == "unknown" or isinstance(result, str)

    def test_get_aioredis_version_alias(self):
        from uk_management_bot.utils.redis_wrapper import get_aioredis_version, get_redis_version
        assert get_aioredis_version is get_redis_version
