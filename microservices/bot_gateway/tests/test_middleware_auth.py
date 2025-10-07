"""
Bot Gateway Service - Auth Middleware Tests
UK Management Bot

Tests for automatic user authentication and session management middleware.
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.middleware.auth import AuthMiddleware
from app.models.bot_session import BotSession


@pytest.mark.asyncio
class TestAuthMiddleware:
    """Test cases for AuthMiddleware"""

    async def test_middleware_creates_new_session_for_new_user(
        self, db_session, redis_client, mock_auth_response, mock_user_response, clean_database
    ):
        """Test that middleware creates new session for new Telegram user"""
        middleware = AuthMiddleware()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = 999999999
        mock_event.from_user.first_name = "NewUser"
        mock_event.from_user.last_name = "Test"
        mock_event.from_user.language_code = "ru"

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Mock Auth Service response
        with patch("app.integrations.auth_client.AuthServiceClient.login_telegram") as mock_auth:
            mock_auth.return_value = mock_auth_response

            with patch("app.integrations.user_client.UserServiceClient.get_by_telegram_id") as mock_user:
                mock_user.return_value = mock_user_response

                # Execute middleware
                result = await middleware(handler, mock_event, data)

                # Verify session was created
                assert "bot_session" in data
                assert "token" in data
                assert data["token"] == mock_auth_response["access_token"]
                assert data["user_id"] == mock_auth_response["user_id"]
                assert data["user_role"] == mock_auth_response["role"]

                # Verify session in database
                from sqlalchemy import select

                stmt = select(BotSession).where(BotSession.telegram_id == 999999999)
                db_session_obj = await db_session.execute(stmt)
                session = db_session_obj.scalar_one_or_none()

                assert session is not None
                assert session.telegram_id == 999999999
                assert session.language_code == "ru"
                assert session.is_active is True

    async def test_middleware_reuses_existing_valid_session(
        self, db_session, redis_client, sample_bot_session, clean_database
    ):
        """Test that middleware reuses existing session with valid token"""
        # Create existing session
        db_session.add(sample_bot_session)
        await db_session.commit()

        middleware = AuthMiddleware()

        # Mock Telegram update with same user
        mock_event = MagicMock()
        mock_event.from_user.id = sample_bot_session.telegram_id
        mock_event.from_user.first_name = "Test"
        mock_event.from_user.last_name = "User"
        mock_event.from_user.language_code = "ru"

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Execute middleware (should NOT call Auth Service)
        with patch("app.integrations.auth_client.AuthServiceClient.login_telegram") as mock_auth:
            result = await middleware(handler, mock_event, data)

            # Verify existing session was used
            assert "bot_session" in data
            assert "token" in data
            assert data["token"] == sample_bot_session.context_json["access_token"]
            assert mock_auth.call_count == 0  # Auth service should NOT be called

    async def test_middleware_refreshes_expired_token(
        self, db_session, redis_client, sample_bot_session, mock_auth_response, clean_database
    ):
        """Test that middleware refreshes expired token"""
        # Create session with expired token
        sample_bot_session.context_json["token_expires_at"] = (
            datetime.utcnow() - timedelta(hours=1)
        ).isoformat()
        db_session.add(sample_bot_session)
        await db_session.commit()

        middleware = AuthMiddleware()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = sample_bot_session.telegram_id
        mock_event.from_user.first_name = "Test"
        mock_event.from_user.last_name = "User"
        mock_event.from_user.language_code = "ru"

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Mock Auth Service response
        with patch("app.integrations.auth_client.AuthServiceClient.login_telegram") as mock_auth:
            mock_auth.return_value = mock_auth_response

            # Execute middleware
            result = await middleware(handler, mock_event, data)

            # Verify token was refreshed
            assert "bot_session" in data
            assert "token" in data
            assert data["token"] == mock_auth_response["access_token"]
            assert mock_auth.call_count == 1  # Auth service SHOULD be called

    async def test_middleware_updates_last_activity(
        self, db_session, redis_client, sample_bot_session, clean_database
    ):
        """Test that middleware updates last_activity_at on each request"""
        db_session.add(sample_bot_session)
        await db_session.commit()

        original_activity = sample_bot_session.last_activity_at

        middleware = AuthMiddleware()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = sample_bot_session.telegram_id
        mock_event.from_user.first_name = "Test"
        mock_event.from_user.last_name = "User"
        mock_event.from_user.language_code = "ru"

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Execute middleware
        await middleware(handler, mock_event, data)

        # Verify last_activity_at was updated
        await db_session.refresh(sample_bot_session)
        assert sample_bot_session.last_activity_at > original_activity

    async def test_middleware_handles_language_change(
        self, db_session, redis_client, sample_bot_session, clean_database
    ):
        """Test that middleware updates language when user changes it"""
        sample_bot_session.language_code = "ru"
        db_session.add(sample_bot_session)
        await db_session.commit()

        middleware = AuthMiddleware()

        # Mock Telegram update with different language
        mock_event = MagicMock()
        mock_event.from_user.id = sample_bot_session.telegram_id
        mock_event.from_user.first_name = "Test"
        mock_event.from_user.last_name = "User"
        mock_event.from_user.language_code = "uz"

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Execute middleware
        await middleware(handler, mock_event, data)

        # Verify language was updated
        await db_session.refresh(sample_bot_session)
        assert sample_bot_session.language_code == "uz"

    async def test_middleware_extends_session_expiration(
        self, db_session, redis_client, sample_bot_session, clean_database
    ):
        """Test that middleware extends session expiration on activity"""
        original_expiration = sample_bot_session.expires_at
        db_session.add(sample_bot_session)
        await db_session.commit()

        middleware = AuthMiddleware()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = sample_bot_session.telegram_id
        mock_event.from_user.first_name = "Test"
        mock_event.from_user.last_name = "User"
        mock_event.from_user.language_code = "ru"

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Execute middleware
        await middleware(handler, mock_event, data)

        # Verify expiration was extended
        await db_session.refresh(sample_bot_session)
        assert sample_bot_session.expires_at > original_expiration

    async def test_middleware_provides_context_to_handler(
        self, db_session, redis_client, sample_bot_session, clean_database
    ):
        """Test that middleware provides complete context to handler"""
        db_session.add(sample_bot_session)
        await db_session.commit()

        middleware = AuthMiddleware()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = sample_bot_session.telegram_id
        mock_event.from_user.first_name = "Test"
        mock_event.from_user.last_name = "User"
        mock_event.from_user.language_code = "ru"

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Execute middleware
        await middleware(handler, mock_event, data)

        # Verify all required context is provided
        assert "bot_session" in data
        assert "token" in data
        assert "user_id" in data
        assert "user_role" in data
        assert "language" in data

        assert data["bot_session"].id == sample_bot_session.id
        assert data["token"] == sample_bot_session.context_json["access_token"]
        assert data["user_id"] == sample_bot_session.context_json["user_id"]
        assert data["user_role"] == sample_bot_session.context_json["role"]
        assert data["language"] == sample_bot_session.language_code

    async def test_middleware_handles_auth_service_failure(
        self, db_session, redis_client, clean_database
    ):
        """Test that middleware handles Auth Service failures gracefully"""
        middleware = AuthMiddleware()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = 123456789
        mock_event.from_user.first_name = "Test"
        mock_event.from_user.last_name = "User"
        mock_event.from_user.language_code = "ru"

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Mock Auth Service failure
        with patch("app.integrations.auth_client.AuthServiceClient.login_telegram") as mock_auth:
            mock_auth.side_effect = Exception("Auth Service unavailable")

            # Execute middleware - should propagate exception
            with pytest.raises(Exception, match="Auth Service unavailable"):
                await middleware(handler, mock_event, data)

    async def test_middleware_increments_session_version(
        self, db_session, redis_client, sample_bot_session, clean_database
    ):
        """Test that middleware increments session version on updates"""
        original_version = sample_bot_session.session_version
        db_session.add(sample_bot_session)
        await db_session.commit()

        middleware = AuthMiddleware()

        # Mock Telegram update
        mock_event = MagicMock()
        mock_event.from_user.id = sample_bot_session.telegram_id
        mock_event.from_user.first_name = "Test"
        mock_event.from_user.last_name = "User"
        mock_event.from_user.language_code = "uz"  # Change language to trigger update

        # Mock data dict
        data = {"db_session": db_session}

        # Mock handler
        handler = AsyncMock(return_value=True)

        # Execute middleware
        await middleware(handler, mock_event, data)

        # Verify version was incremented
        await db_session.refresh(sample_bot_session)
        assert sample_bot_session.session_version == original_version + 1
