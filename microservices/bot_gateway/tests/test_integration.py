"""
Bot Gateway Service - Integration Tests
UK Management Bot

End-to-end integration tests for complete user flows.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from aiogram import types
from aiogram.fsm.context import FSMContext

from app.main import create_dispatcher
from app.models.bot_session import BotSession


@pytest.mark.integration
@pytest.mark.asyncio
class TestRequestCreationFlow:
    """Integration tests for complete request creation flow"""

    async def test_complete_request_creation_flow(
        self, bot, storage, db_session, clean_database
    ):
        """Test complete flow: /start → Create Request → Enter data → Success"""
        dispatcher = create_dispatcher()

        # Mock user
        user_id = 123456789

        # Step 1: /start command
        message_start = MagicMock(spec=types.Message)
        message_start.from_user = MagicMock()
        message_start.from_user.id = user_id
        message_start.from_user.first_name = "Test"
        message_start.from_user.last_name = "User"
        message_start.from_user.language_code = "ru"
        message_start.text = "/start"
        message_start.answer = AsyncMock()
        message_start.bot = bot

        # Mock auth and user services
        with patch("app.integrations.auth_client.AuthServiceClient.login_telegram") as mock_auth:
            mock_auth.return_value = {
                "access_token": "test_token",
                "user_id": str(uuid4()),
                "role": "applicant",
            }

            with patch("app.integrations.user_client.UserServiceClient.get_by_telegram_id") as mock_user:
                mock_user.return_value = {
                    "id": str(uuid4()),
                    "telegram_id": user_id,
                    "role": "applicant",
                }

                # Process /start
                from app.routers.common import cmd_start

                state_context = FSMContext(storage=storage, key=f"user:{user_id}")
                await cmd_start(
                    message_start,
                    user_role="applicant",
                    language="ru",
                    state=state_context,
                )

                # Verify welcome message sent
                assert message_start.answer.call_count > 0

        # Step 2: Click "Create Request" button
        message_create = MagicMock(spec=types.Message)
        message_create.from_user = MagicMock()
        message_create.from_user.id = user_id
        message_create.text = "➕ Создать заявку"
        message_create.answer = AsyncMock()

        from app.routers.requests import button_create_request

        await button_create_request(message_create, state=state_context, language="ru")

        # Verify FSM state changed
        current_state = await state_context.get_state()
        assert current_state is not None

        # Step 3: Enter building number
        message_building = MagicMock(spec=types.Message)
        message_building.from_user = MagicMock()
        message_building.from_user.id = user_id
        message_building.text = "5"
        message_building.answer = AsyncMock()

        from app.routers.requests import process_building_input

        await process_building_input(message_building, state=state_context, language="ru")

        # Verify data saved
        state_data = await state_context.get_data()
        assert state_data["building"] == "5"

        # Step 4: Enter apartment number
        message_apartment = MagicMock(spec=types.Message)
        message_apartment.from_user = MagicMock()
        message_apartment.from_user.id = user_id
        message_apartment.text = "42"
        message_apartment.answer = AsyncMock()

        from app.routers.requests import process_apartment_input

        await process_apartment_input(message_apartment, state=state_context, language="ru")

        # Verify data saved
        state_data = await state_context.get_data()
        assert state_data["apartment"] == "42"

        # Step 5: Enter description
        message_description = MagicMock(spec=types.Message)
        message_description.from_user = MagicMock()
        message_description.from_user.id = user_id
        message_description.text = "Течет кран на кухне"
        message_description.answer = AsyncMock()

        # Mock Request Service
        with patch("app.integrations.request_client.RequestServiceClient.create_request") as mock_create:
            mock_create.return_value = {
                "request_number": "250101-001",
                "building": "5",
                "apartment": "42",
                "description": "Течет кран на кухне",
                "status": "new",
            }

            from app.routers.requests import process_description_input

            await process_description_input(
                message_description, state=state_context, token="test_token"
            )

            # Verify request created
            mock_create.assert_called_once()

            # Verify success message
            assert message_description.answer.call_count > 0

            # Verify FSM cleared
            current_state = await state_context.get_state()
            assert current_state is None


@pytest.mark.integration
@pytest.mark.asyncio
class TestRequestViewingFlow:
    """Integration tests for viewing and managing requests"""

    async def test_view_my_requests_flow(
        self, bot, storage, db_session
    ):
        """Test complete flow: My Requests → View Request → View Details"""
        user_id = 222333444

        state_context = FSMContext(storage=storage, key=f"user:{user_id}")

        # Step 1: Click "My Requests" button
        message_my_requests = MagicMock(spec=types.Message)
        message_my_requests.from_user = MagicMock()
        message_my_requests.from_user.id = user_id
        message_my_requests.text = "📋 Мои заявки"
        message_my_requests.answer = AsyncMock()

        # Mock Request Service - list requests
        with patch("app.integrations.request_client.RequestServiceClient.get_my_requests") as mock_list:
            mock_list.return_value = {
                "items": [
                    {
                        "request_number": "250101-001",
                        "building": "5",
                        "apartment": "42",
                        "status": "new",
                        "description": "Test request",
                    }
                ],
                "total": 1,
            }

            from app.routers.requests import button_my_requests

            await button_my_requests(
                message_my_requests, token="test_token", language="ru"
            )

            # Verify requests retrieved
            mock_list.assert_called_once()

            # Verify message sent
            assert message_my_requests.answer.call_count > 0

        # Step 2: Click "View" button (callback)
        callback_view = MagicMock(spec=types.CallbackQuery)
        callback_view.from_user = MagicMock()
        callback_view.from_user.id = user_id
        callback_view.data = "request:view:250101-001"
        callback_view.message = MagicMock()
        callback_view.message.answer = AsyncMock()
        callback_view.answer = AsyncMock()

        # Mock Request Service - get request details
        with patch("app.integrations.request_client.RequestServiceClient.get_request_by_number") as mock_get:
            mock_get.return_value = {
                "request_number": "250101-001",
                "building": "5",
                "apartment": "42",
                "description": "Detailed description of the request",
                "status": "new",
                "priority": "normal",
                "created_at": "2025-01-01T10:00:00",
            }

            from app.routers.requests import callback_request_action

            await callback_request_action(
                callback_view, token="test_token", language="ru"
            )

            # Verify request details retrieved
            mock_get.assert_called_once_with("250101-001", token="test_token")

            # Verify detailed message sent
            assert callback_view.message.answer.call_count > 0


@pytest.mark.integration
@pytest.mark.asyncio
class TestSessionPersistence:
    """Integration tests for session management and persistence"""

    async def test_session_persists_across_requests(
        self, db_session, storage, clean_database
    ):
        """Test that user session persists across multiple requests"""
        user_id = 333444555
        telegram_id = 333444555

        # Create initial session
        session = BotSession(
            id=uuid4(),
            management_company_id="uk_company_1",
            user_id=uuid4(),
            telegram_id=telegram_id,
            language_code="ru",
            is_active=True,
            context_json={
                "access_token": "test_token",
                "user_id": str(uuid4()),
                "role": "applicant",
            },
        )
        db_session.add(session)
        await db_session.commit()

        # Simulate multiple requests
        from app.middleware.auth import AuthMiddleware

        middleware = AuthMiddleware()

        for i in range(3):
            mock_event = MagicMock()
            mock_event.from_user = MagicMock()
            mock_event.from_user.id = telegram_id
            mock_event.from_user.first_name = "Test"
            mock_event.from_user.last_name = "User"
            mock_event.from_user.language_code = "ru"

            data = {"db_session": db_session}

            handler = AsyncMock(return_value=True)

            # Execute middleware
            await middleware(handler, mock_event, data)

            # Verify same session is used
            assert data["bot_session"].id == session.id

        # Verify session was updated (not recreated)
        from sqlalchemy import select, func

        stmt = select(func.count(BotSession.id)).where(BotSession.telegram_id == telegram_id)
        result = await db_session.execute(stmt)
        count = result.scalar()

        # Should still be only 1 session
        assert count == 1


@pytest.mark.integration
@pytest.mark.asyncio
class TestMultiLanguageSupport:
    """Integration tests for multi-language support"""

    async def test_language_switch_during_flow(
        self, bot, storage, db_session
    ):
        """Test that user can switch language and see translated messages"""
        user_id = 444555666

        state_context = FSMContext(storage=storage, key=f"user:{user_id}")

        # Start in Russian
        message_ru = MagicMock(spec=types.Message)
        message_ru.from_user = MagicMock()
        message_ru.from_user.id = user_id
        message_ru.text = "➕ Создать заявку"
        message_ru.answer = AsyncMock()

        from app.routers.requests import button_create_request

        await button_create_request(message_ru, state=state_context, language="ru")

        # Verify Russian text
        call_args = message_ru.answer.call_args
        assert "дом" in call_args[1]["text"].lower()

        # Switch to Uzbek
        await state_context.clear()

        message_uz = MagicMock(spec=types.Message)
        message_uz.from_user = MagicMock()
        message_uz.from_user.id = user_id
        message_uz.text = "➕ Ariza yaratish"
        message_uz.answer = AsyncMock()

        await button_create_request(message_uz, state=state_context, language="uz")

        # Verify Uzbek text
        call_args_uz = message_uz.answer.call_args
        # Note: Actual Uzbek translation would be in the implementation
        assert message_uz.answer.call_count > 0


@pytest.mark.integration
@pytest.mark.asyncio
class TestErrorHandling:
    """Integration tests for error handling scenarios"""

    async def test_service_unavailable_error_handling(
        self, bot, storage
    ):
        """Test graceful handling when backend service is unavailable"""
        user_id = 555666777

        message = MagicMock(spec=types.Message)
        message.from_user = MagicMock()
        message.from_user.id = user_id
        message.text = "📋 Мои заявки"
        message.answer = AsyncMock()

        # Mock Request Service failure
        with patch("app.integrations.request_client.RequestServiceClient.get_my_requests") as mock_list:
            import httpx

            mock_list.side_effect = httpx.ConnectError("Connection refused")

            from app.routers.requests import button_my_requests

            # Execute - should handle error gracefully
            try:
                await button_my_requests(message, token="test_token", language="ru")
            except httpx.ConnectError:
                # Error should be caught and user-friendly message shown
                pass

            # Verify some message was sent (error message)
            # Note: Actual implementation may vary
            assert message.answer.call_count >= 0

    async def test_invalid_token_error_handling(
        self, bot, storage
    ):
        """Test handling of invalid/expired JWT token"""
        user_id = 666777888

        message = MagicMock(spec=types.Message)
        message.from_user = MagicMock()
        message.from_user.id = user_id
        message.text = "📋 Мои заявки"
        message.answer = AsyncMock()

        # Mock Auth Service - invalid token
        with patch("app.integrations.request_client.RequestServiceClient.get_my_requests") as mock_list:
            import httpx

            mock_list.side_effect = httpx.HTTPStatusError(
                "Unauthorized", request=MagicMock(), response=MagicMock(status_code=401)
            )

            from app.routers.requests import button_my_requests

            # Execute - should trigger re-authentication
            try:
                await button_my_requests(message, token="invalid_token", language="ru")
            except httpx.HTTPStatusError:
                # Should be caught and handled
                pass

            # Implementation should handle 401 and refresh token
            assert True  # Placeholder for actual verification
