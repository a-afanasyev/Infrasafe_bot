"""
Unit tests for uk_management_bot/handlers/health.py

Covers pure helper functions and handler functions:
  check_database_health, check_redis_health, get_system_info,
  health_check_command, detailed_health_check_command,
  ping_command, get_health_status.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from aiogram.types import Message, User as TgUser
from sqlalchemy.orm import Session


# ─── Helpers ────────────────────────────────────────────────────────────────

def _make_tg_user(user_id=1):
    u = MagicMock(spec=TgUser)
    u.id = user_id
    return u


def _make_message(user_id=1):
    msg = MagicMock(spec=Message)
    msg.from_user = _make_tg_user(user_id=user_id)
    msg.answer = AsyncMock()
    return msg


def _make_db(ping_ok=True):
    """Create a mock SQLAlchemy Session."""
    db = MagicMock(spec=Session)
    if ping_ok:
        result = MagicMock()
        result.fetchone.return_value = (1,)
        db.execute.return_value = result
    else:
        db.execute.side_effect = Exception("DB connection refused")
    return db


# ─── check_database_health ───────────────────────────────────────────────────

class TestCheckDatabaseHealth:
    """Tests for check_database_health()"""

    @pytest.mark.asyncio
    async def test_healthy_db_returns_healthy_status(self):
        """Returns 'healthy' when DB query succeeds."""
        from uk_management_bot.handlers.health import check_database_health

        db = _make_db(ping_ok=True)
        result = await check_database_health(db)

        assert result["status"] == "healthy"
        assert "response_time_ms" in result
        assert isinstance(result["response_time_ms"], float)

    @pytest.mark.asyncio
    async def test_unhealthy_db_returns_unhealthy_status(self):
        """Returns 'unhealthy' with error key when DB query fails."""
        from uk_management_bot.handlers.health import check_database_health

        db = _make_db(ping_ok=False)
        result = await check_database_health(db)

        assert result["status"] == "unhealthy"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_timestamp_is_present(self):
        """check_database_health always includes a timestamp."""
        from uk_management_bot.handlers.health import check_database_health

        db = _make_db()
        result = await check_database_health(db)

        assert "timestamp" in result
        assert isinstance(result["timestamp"], str)


# ─── check_redis_health ──────────────────────────────────────────────────────

class TestCheckRedisHealth:
    """Tests for check_redis_health()"""

    @pytest.mark.asyncio
    async def test_redis_disabled_returns_disabled_status(self):
        """Returns 'disabled' status when USE_REDIS_RATE_LIMIT is False."""
        from uk_management_bot.handlers.health import check_redis_health

        with patch(
            "uk_management_bot.handlers.health.settings"
        ) as mock_settings:
            mock_settings.USE_REDIS_RATE_LIMIT = False

            result = await check_redis_health()

        assert result["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_redis_enabled_client_none_returns_disabled(self):
        """Returns 'disabled' when Redis client cannot be obtained."""
        from uk_management_bot.handlers.health import check_redis_health

        with patch(
            "uk_management_bot.handlers.health.settings"
        ) as mock_settings, patch(
            "uk_management_bot.utils.redis_rate_limiter.get_redis_client",
            new_callable=AsyncMock,
            return_value=None,
        ):
            mock_settings.USE_REDIS_RATE_LIMIT = True

            result = await check_redis_health()

        assert result["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_redis_healthy_returns_healthy_status(self):
        """Returns 'healthy' when Redis ping succeeds."""
        from uk_management_bot.handlers.health import check_redis_health

        fake_redis = AsyncMock()
        fake_redis.ping = AsyncMock(return_value=True)

        with patch(
            "uk_management_bot.handlers.health.settings"
        ) as mock_settings, patch(
            "uk_management_bot.utils.redis_rate_limiter.get_redis_client",
            new_callable=AsyncMock,
            return_value=fake_redis,
        ):
            mock_settings.USE_REDIS_RATE_LIMIT = True

            result = await check_redis_health()

        assert result["status"] == "healthy"
        assert "response_time_ms" in result

    @pytest.mark.asyncio
    async def test_redis_exception_returns_unhealthy(self):
        """Returns 'unhealthy' when Redis raises an exception."""
        from uk_management_bot.handlers.health import check_redis_health

        fake_redis = AsyncMock()
        fake_redis.ping = AsyncMock(side_effect=ConnectionError("redis down"))

        with patch(
            "uk_management_bot.handlers.health.settings"
        ) as mock_settings, patch(
            "uk_management_bot.utils.redis_rate_limiter.get_redis_client",
            new_callable=AsyncMock,
            return_value=fake_redis,
        ):
            mock_settings.USE_REDIS_RATE_LIMIT = True

            result = await check_redis_health()

        assert result["status"] == "unhealthy"
        assert "error" in result


# ─── get_system_info ─────────────────────────────────────────────────────────

class TestGetSystemInfo:
    """Tests for get_system_info()"""

    @pytest.mark.asyncio
    async def test_returns_required_fields(self):
        """get_system_info returns expected keys."""
        from uk_management_bot.handlers.health import get_system_info

        info = await get_system_info()

        assert "uptime_seconds" in info
        assert "uptime_human" in info
        assert "debug_mode" in info
        assert "log_level" in info
        assert "supported_languages" in info
        assert "timestamp" in info

    @pytest.mark.asyncio
    async def test_uptime_is_positive(self):
        """get_system_info returns a non-negative uptime."""
        from uk_management_bot.handlers.health import get_system_info

        info = await get_system_info()

        assert info["uptime_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_uptime_human_format(self):
        """uptime_human contains hours, minutes, and seconds markers."""
        from uk_management_bot.handlers.health import get_system_info

        info = await get_system_info()

        assert "h" in info["uptime_human"]
        assert "m" in info["uptime_human"]
        assert "s" in info["uptime_human"]


# ─── health_check_command ────────────────────────────────────────────────────

class TestHealthCheckCommand:
    """Tests for health_check_command handler."""

    @pytest.mark.asyncio
    async def test_healthy_system_sends_message(self):
        """health_check_command sends a message when system is healthy."""
        from uk_management_bot.handlers.health import health_check_command

        msg = _make_message()
        db = _make_db()

        healthy_db = {"status": "healthy", "response_time_ms": 1.23, "timestamp": "2025-01-01T00:00:00"}
        disabled_redis = {"status": "disabled", "message": "Redis disabled"}
        system_info = {
            "uptime_seconds": 3600.0,
            "uptime_human": "1h 0m 0s",
            "debug_mode": False,
            "log_level": "INFO",
            "supported_languages": ["ru", "uz"],
            "timestamp": "2025-01-01T00:00:00",
        }

        with patch(
            "uk_management_bot.handlers.health.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.handlers.health.check_database_health",
            new_callable=AsyncMock,
            return_value=healthy_db,
        ), patch(
            "uk_management_bot.handlers.health.check_redis_health",
            new_callable=AsyncMock,
            return_value=disabled_redis,
        ), patch(
            "uk_management_bot.handlers.health.get_system_info",
            new_callable=AsyncMock,
            return_value=system_info,
        ), patch(
            "uk_management_bot.handlers.health.settings"
        ) as mock_settings:
            mock_settings.USE_REDIS_RATE_LIMIT = False

            await health_check_command(msg, db)

        msg.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_unhealthy_db_sends_unhealthy_status(self):
        """health_check_command sends UNHEALTHY when DB is down."""
        from uk_management_bot.handlers.health import health_check_command

        msg = _make_message()
        db = _make_db()

        unhealthy_db = {"status": "unhealthy", "error": "connection error", "timestamp": "2025-01-01T00:00:00"}
        disabled_redis = {"status": "disabled"}
        system_info = {
            "uptime_seconds": 100.0,
            "uptime_human": "0h 1m 40s",
            "debug_mode": False,
            "log_level": "INFO",
            "supported_languages": ["ru"],
            "timestamp": "2025-01-01T00:00:00",
        }

        with patch(
            "uk_management_bot.handlers.health.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.handlers.health.check_database_health",
            new_callable=AsyncMock,
            return_value=unhealthy_db,
        ), patch(
            "uk_management_bot.handlers.health.check_redis_health",
            new_callable=AsyncMock,
            return_value=disabled_redis,
        ), patch(
            "uk_management_bot.handlers.health.get_system_info",
            new_callable=AsyncMock,
            return_value=system_info,
        ), patch(
            "uk_management_bot.handlers.health.settings"
        ) as mock_settings:
            mock_settings.USE_REDIS_RATE_LIMIT = False

            await health_check_command(msg, db)

        msg.answer.assert_called_once()
        sent_text = msg.answer.call_args[0][0]
        assert "UNHEALTHY" in sent_text

    @pytest.mark.asyncio
    async def test_exception_in_check_sends_error_message(self):
        """health_check_command handles unexpected exceptions gracefully."""
        from uk_management_bot.handlers.health import health_check_command

        msg = _make_message()
        db = _make_db()

        with patch(
            "uk_management_bot.handlers.health.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.handlers.health.check_database_health",
            new_callable=AsyncMock,
            side_effect=RuntimeError("unexpected error"),
        ):
            await health_check_command(msg, db)

        msg.answer.assert_called_once()


# ─── detailed_health_check_command ───────────────────────────────────────────

class TestDetailedHealthCheckCommand:
    """Tests for detailed_health_check_command handler."""

    @pytest.mark.asyncio
    async def test_non_admin_receives_permission_denied(self):
        """detailed_health_check_command denies access to non-admin/manager users."""
        from uk_management_bot.handlers.health import detailed_health_check_command

        msg = _make_message()
        db = _make_db()

        with patch("uk_management_bot.handlers.health.get_user_language", return_value="ru"):
            await detailed_health_check_command(msg, db, roles=["applicant"])

        msg.answer.assert_called_once()
        # No detailed info sent — just permission denied
        sent_text = msg.answer.call_args[0][0]
        assert isinstance(sent_text, str)

    @pytest.mark.asyncio
    async def test_no_roles_receives_permission_denied(self):
        """detailed_health_check_command denies access when roles is None."""
        from uk_management_bot.handlers.health import detailed_health_check_command

        msg = _make_message()
        db = _make_db()

        with patch("uk_management_bot.handlers.health.get_user_language", return_value="ru"):
            await detailed_health_check_command(msg, db, roles=None)

        msg.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_manager_receives_detailed_report(self):
        """detailed_health_check_command sends detailed info to manager."""
        from uk_management_bot.handlers.health import detailed_health_check_command

        msg = _make_message()
        db = _make_db()

        healthy_db = {"status": "healthy", "response_time_ms": 1.0, "timestamp": "2025-01-01T00:00:00"}
        disabled_redis = {"status": "disabled"}
        system_info = {
            "uptime_seconds": 500.0,
            "uptime_human": "0h 8m 20s",
            "debug_mode": False,
            "log_level": "INFO",
            "supported_languages": ["ru"],
            "timestamp": "2025-01-01T00:00:00",
        }

        with patch(
            "uk_management_bot.handlers.health.get_user_language", return_value="ru"
        ), patch(
            "uk_management_bot.handlers.health.check_database_health",
            new_callable=AsyncMock,
            return_value=healthy_db,
        ), patch(
            "uk_management_bot.handlers.health.check_redis_health",
            new_callable=AsyncMock,
            return_value=disabled_redis,
        ), patch(
            "uk_management_bot.handlers.health.get_system_info",
            new_callable=AsyncMock,
            return_value=system_info,
        ), patch(
            "uk_management_bot.handlers.health.settings"
        ) as mock_settings:
            mock_settings.INVITE_SECRET = "secret_key"
            mock_settings.ADMIN_PASSWORD = "strong_password_123!"
            mock_settings.USE_REDIS_RATE_LIMIT = False
            mock_settings.ENABLE_NOTIFICATIONS = True
            mock_settings.ADMIN_USER_IDS = [111, 222]

            await detailed_health_check_command(msg, db, roles=["manager"])

        msg.answer.assert_called_once()


# ─── ping_command ─────────────────────────────────────────────────────────────

class TestPingCommand:
    """Tests for ping_command handler."""

    @pytest.mark.asyncio
    async def test_ping_sends_response(self):
        """ping_command sends a reply message."""
        from uk_management_bot.handlers.health import ping_command

        msg = _make_message()
        db = _make_db()

        with patch("uk_management_bot.handlers.health.get_user_language", return_value="ru"):
            await ping_command(msg, db)

        msg.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_ping_response_is_non_empty_string(self):
        """ping_command sends a non-empty string."""
        from uk_management_bot.handlers.health import ping_command

        msg = _make_message()
        db = _make_db()

        with patch("uk_management_bot.handlers.health.get_user_language", return_value="ru"):
            await ping_command(msg, db)

        sent_text = msg.answer.call_args[0][0]
        assert isinstance(sent_text, str)
        assert len(sent_text) > 0


# ─── get_health_status ───────────────────────────────────────────────────────

class TestGetHealthStatus:
    """Tests for get_health_status() utility."""

    @pytest.mark.asyncio
    async def test_returns_healthy_when_all_components_healthy(self):
        """get_health_status returns 'healthy' overall when all components are up."""
        from uk_management_bot.handlers.health import get_health_status

        db = _make_db()

        healthy_db = {"status": "healthy", "response_time_ms": 1.0, "timestamp": "2025-01-01T00:00:00"}
        disabled_redis = {"status": "disabled"}
        system_info = {
            "uptime_seconds": 100.0,
            "uptime_human": "0h 1m 40s",
            "debug_mode": False,
            "log_level": "INFO",
            "supported_languages": ["ru"],
            "timestamp": "2025-01-01T00:00:00",
        }

        with patch(
            "uk_management_bot.handlers.health.check_database_health",
            new_callable=AsyncMock,
            return_value=healthy_db,
        ), patch(
            "uk_management_bot.handlers.health.check_redis_health",
            new_callable=AsyncMock,
            return_value=disabled_redis,
        ), patch(
            "uk_management_bot.handlers.health.get_system_info",
            new_callable=AsyncMock,
            return_value=system_info,
        ), patch(
            "uk_management_bot.handlers.health.settings"
        ) as mock_settings:
            mock_settings.USE_REDIS_RATE_LIMIT = False

            status = await get_health_status(db)

        assert status["status"] == "healthy"
        assert "components" in status
        assert "summary" in status

    @pytest.mark.asyncio
    async def test_returns_unhealthy_when_db_fails(self):
        """get_health_status returns 'unhealthy' when DB is down."""
        from uk_management_bot.handlers.health import get_health_status

        db = _make_db()

        unhealthy_db = {"status": "unhealthy", "error": "timeout", "timestamp": "2025-01-01T00:00:00"}
        disabled_redis = {"status": "disabled"}
        system_info = {
            "uptime_seconds": 100.0,
            "uptime_human": "0h 1m 40s",
            "debug_mode": False,
            "log_level": "INFO",
            "supported_languages": ["ru"],
            "timestamp": "2025-01-01T00:00:00",
        }

        with patch(
            "uk_management_bot.handlers.health.check_database_health",
            new_callable=AsyncMock,
            return_value=unhealthy_db,
        ), patch(
            "uk_management_bot.handlers.health.check_redis_health",
            new_callable=AsyncMock,
            return_value=disabled_redis,
        ), patch(
            "uk_management_bot.handlers.health.get_system_info",
            new_callable=AsyncMock,
            return_value=system_info,
        ), patch(
            "uk_management_bot.handlers.health.settings"
        ) as mock_settings:
            mock_settings.USE_REDIS_RATE_LIMIT = False

            status = await get_health_status(db)

        assert status["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_returns_degraded_when_redis_fails_but_db_ok(self):
        """get_health_status returns 'degraded' when Redis is unhealthy but DB is fine."""
        from uk_management_bot.handlers.health import get_health_status

        db = _make_db()

        healthy_db = {"status": "healthy", "response_time_ms": 1.0, "timestamp": "2025-01-01T00:00:00"}
        unhealthy_redis = {"status": "unhealthy", "error": "connection refused", "timestamp": "2025-01-01T00:00:00"}
        system_info = {
            "uptime_seconds": 100.0,
            "uptime_human": "0h 1m 40s",
            "debug_mode": False,
            "log_level": "INFO",
            "supported_languages": ["ru"],
            "timestamp": "2025-01-01T00:00:00",
        }

        with patch(
            "uk_management_bot.handlers.health.check_database_health",
            new_callable=AsyncMock,
            return_value=healthy_db,
        ), patch(
            "uk_management_bot.handlers.health.check_redis_health",
            new_callable=AsyncMock,
            return_value=unhealthy_redis,
        ), patch(
            "uk_management_bot.handlers.health.get_system_info",
            new_callable=AsyncMock,
            return_value=system_info,
        ), patch(
            "uk_management_bot.handlers.health.settings"
        ) as mock_settings:
            mock_settings.USE_REDIS_RATE_LIMIT = True

            status = await get_health_status(db)

        assert status["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_exception_returns_unhealthy_with_error_key(self):
        """get_health_status handles internal exceptions gracefully."""
        from uk_management_bot.handlers.health import get_health_status

        db = _make_db()

        with patch(
            "uk_management_bot.handlers.health.check_database_health",
            new_callable=AsyncMock,
            side_effect=RuntimeError("unexpected"),
        ):
            status = await get_health_status(db)

        assert status["status"] == "unhealthy"
        assert "error" in status
