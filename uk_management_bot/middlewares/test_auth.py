"""
Unit tests for middlewares/auth.py

Covers:
- auth_middleware: user loading, blocked-user early exit, fail-safe defaults
- role_mode_middleware: role/active_role context propagation
- require_role: decorator enforces role checks, allows/denies access
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import Message, CallbackQuery


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_message(telegram_id: int = 1001, language_code: str = "ru") -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock()
    msg.from_user.id = telegram_id
    msg.from_user.language_code = language_code
    msg.answer = AsyncMock()
    return msg


def _make_callback(telegram_id: int = 1001, language_code: str = "ru") -> MagicMock:
    cb = MagicMock(spec=CallbackQuery)
    cb.from_user = MagicMock()
    cb.from_user.id = telegram_id
    cb.from_user.language_code = language_code
    cb.answer = AsyncMock()
    return cb


def _make_user(
    telegram_id: int = 1001,
    status: str = "approved",
    roles: str = '["applicant"]',
    active_role: str = "applicant",
    role: str = "applicant",
    language: str = "ru",
) -> MagicMock:
    user = MagicMock()
    user.telegram_id = telegram_id
    user.status = status
    user.roles = roles
    user.active_role = active_role
    user.role = role
    user.language = language
    return user


async def _noop_handler(event, data):
    """Simple handler that records it was called."""
    data["_handler_called"] = True
    return "ok"


# ---------------------------------------------------------------------------
# auth_middleware
# ---------------------------------------------------------------------------

class TestAuthMiddleware:
    @pytest.fixture(autouse=True)
    def patch_get_text(self):
        with patch("uk_management_bot.middlewares.auth.get_text", return_value="blocked") as p:
            yield p

    @pytest.mark.asyncio
    async def test_sets_user_and_status_for_approved_user(self):
        db = MagicMock()
        user = _make_user(telegram_id=1001, status="approved")
        db.query.return_value.filter.return_value.first.return_value = user

        msg = _make_message(telegram_id=1001)
        data = {"db": db}

        from uk_management_bot.middlewares.auth import auth_middleware
        result = await auth_middleware(_noop_handler, msg, data)

        assert data["user"] is user
        assert data["user_status"] == "approved"
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_sets_none_when_no_db(self):
        msg = _make_message(telegram_id=1001)
        data = {}  # no db key

        from uk_management_bot.middlewares.auth import auth_middleware
        result = await auth_middleware(_noop_handler, msg, data)

        assert data["user"] is None
        assert data["user_status"] is None
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_sets_none_when_user_not_found(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        msg = _make_message(telegram_id=9999)
        data = {"db": db}

        from uk_management_bot.middlewares.auth import auth_middleware
        result = await auth_middleware(_noop_handler, msg, data)

        assert data["user"] is None
        assert data["user_status"] is None
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_blocked_user_message_early_exit(self):
        db = MagicMock()
        user = _make_user(telegram_id=1001, status="blocked")
        db.query.return_value.filter.return_value.first.return_value = user

        msg = _make_message(telegram_id=1001)
        data = {"db": db}

        from uk_management_bot.middlewares.auth import auth_middleware
        result = await auth_middleware(_noop_handler, msg, data)

        # Handler must NOT be called, event.answer must be called
        assert result is None
        msg.answer.assert_called_once()
        assert data.get("_handler_called") is None

    @pytest.mark.asyncio
    async def test_blocked_user_callback_early_exit(self):
        db = MagicMock()
        user = _make_user(telegram_id=1001, status="blocked")
        db.query.return_value.filter.return_value.first.return_value = user

        cb = _make_callback(telegram_id=1001)
        data = {"db": db}

        from uk_management_bot.middlewares.auth import auth_middleware
        result = await auth_middleware(_noop_handler, cb, data)

        assert result is None
        cb.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_event_type_still_calls_handler(self):
        unknown_event = MagicMock()  # not Message or CallbackQuery
        data = {}

        from uk_management_bot.middlewares.auth import auth_middleware
        result = await auth_middleware(_noop_handler, unknown_event, data)

        assert data.get("_handler_called") is True

    @pytest.mark.asyncio
    async def test_fail_safe_on_db_error(self):
        db = MagicMock()
        db.query.side_effect = Exception("db failure")

        msg = _make_message(telegram_id=1001)
        data = {"db": db}

        from uk_management_bot.middlewares.auth import auth_middleware
        result = await auth_middleware(_noop_handler, msg, data)

        # Must not raise; handler must still be called
        assert data["user"] is None
        assert data["user_status"] is None
        assert result == "ok"


# ---------------------------------------------------------------------------
# role_mode_middleware
# ---------------------------------------------------------------------------

class TestRoleModeMiddleware:
    @pytest.mark.asyncio
    async def test_sets_roles_from_user(self):
        user = _make_user(roles='["applicant","executor"]', active_role="executor")
        data = {"user": user}

        from uk_management_bot.middlewares.auth import role_mode_middleware
        await role_mode_middleware(_noop_handler, MagicMock(), data)

        assert "executor" in data["roles"]
        assert "applicant" in data["roles"]
        assert data["active_role"] == "executor"

    @pytest.mark.asyncio
    async def test_defaults_when_no_user(self):
        data = {"user": None}

        from uk_management_bot.middlewares.auth import role_mode_middleware
        await role_mode_middleware(_noop_handler, MagicMock(), data)

        assert data["roles"] == ["applicant"]
        assert data["active_role"] == "applicant"

    @pytest.mark.asyncio
    async def test_calls_handler(self):
        data = {"user": None}

        from uk_management_bot.middlewares.auth import role_mode_middleware
        result = await role_mode_middleware(_noop_handler, MagicMock(), data)

        assert result == "ok"

    @pytest.mark.asyncio
    async def test_single_role_user(self):
        user = _make_user(roles='["manager"]', active_role="manager")
        data = {"user": user}

        from uk_management_bot.middlewares.auth import role_mode_middleware
        await role_mode_middleware(_noop_handler, MagicMock(), data)

        assert data["roles"] == ["manager"]
        assert data["active_role"] == "manager"


# ---------------------------------------------------------------------------
# require_role decorator
# ---------------------------------------------------------------------------

class TestRequireRole:
    """Tests for the require_role role-check decorator."""

    @pytest.fixture(autouse=True)
    def patch_get_text(self):
        with patch("uk_management_bot.middlewares.auth.get_text", return_value="no_access") as p:
            yield p

    @pytest.mark.asyncio
    async def test_allows_access_when_role_matches(self):
        from uk_management_bot.middlewares.auth import require_role

        handler_called = []

        @require_role(["manager"])
        async def my_handler(event, **kwargs):
            handler_called.append(True)
            return "allowed"

        msg = _make_message()
        result = await my_handler(msg, roles=["manager"])
        assert result == "allowed"
        assert handler_called

    @pytest.mark.asyncio
    async def test_denies_access_when_role_missing(self):
        from uk_management_bot.middlewares.auth import require_role

        @require_role(["manager"])
        async def my_handler(event, **kwargs):
            return "allowed"

        msg = _make_message()
        result = await my_handler(msg, roles=["applicant"])
        assert result is None
        msg.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_denies_access_when_roles_empty(self):
        from uk_management_bot.middlewares.auth import require_role

        @require_role(["executor"])
        async def my_handler(event, **kwargs):
            return "allowed"

        msg = _make_message()
        result = await my_handler(msg, roles=[])
        assert result is None

    @pytest.mark.asyncio
    async def test_allows_when_one_of_multiple_required_roles_present(self):
        from uk_management_bot.middlewares.auth import require_role

        @require_role(["admin", "manager"])
        async def my_handler(event, **kwargs):
            return "allowed"

        msg = _make_message()
        result = await my_handler(msg, roles=["manager"])
        assert result == "allowed"

    @pytest.mark.asyncio
    async def test_callback_query_answer_on_denial(self):
        from uk_management_bot.middlewares.auth import require_role

        @require_role(["admin"])
        async def my_handler(event, **kwargs):
            return "allowed"

        cb = _make_callback()
        result = await my_handler(cb, roles=["applicant"])
        assert result is None
        cb.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_preserves_function_name(self):
        """wraps() must preserve the original function name."""
        from uk_management_bot.middlewares.auth import require_role

        @require_role(["executor"])
        async def execute_task(event, **kwargs):
            pass

        assert execute_task.__name__ == "execute_task"

    @pytest.mark.asyncio
    async def test_roles_loaded_from_db_when_not_in_kwargs(self):
        """When roles not in kwargs, decorator should try to load from DB."""
        from uk_management_bot.middlewares.auth import require_role

        # Build a fake DB that returns a user with manager role
        db = MagicMock()
        mock_user = _make_user(telegram_id=1001, roles='["manager"]')

        with patch(
            "uk_management_bot.middlewares.auth.get_user_roles",
            return_value=["manager"],
        ):
            db.query.return_value.filter.return_value.first.return_value = mock_user

            @require_role(["manager"])
            async def my_handler(event, **kwargs):
                return "allowed"

            msg = _make_message(telegram_id=1001)
            result = await my_handler(msg, db=db)

        assert result == "allowed"
