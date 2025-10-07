"""
Bot Gateway Service - Handler Tests
UK Management Bot

Tests for command and message handlers.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from aiogram import types
from aiogram.fsm.context import FSMContext

from app.routers.common import router as common_router
from app.routers.requests import router as requests_router
from app.states.request_states import RequestCreationStates


@pytest.mark.asyncio
class TestCommonHandlers:
    """Test cases for common handlers (/start, /help, /menu, /language)"""

    async def test_start_command_handler(
        self, bot, dispatcher, storage, db_session
    ):
        """Test /start command handler"""
        # Mock message
        message = MagicMock(spec=types.Message)
        message.from_user = MagicMock()
        message.from_user.id = 123456789
        message.from_user.first_name = "Test"
        message.from_user.last_name = "User"
        message.from_user.language_code = "ru"
        message.text = "/start"
        message.answer = AsyncMock()

        # Mock FSM context
        state = MagicMock(spec=FSMContext)
        state.clear = AsyncMock()

        # Mock handler data
        data = {
            "bot_session": MagicMock(),
            "token": "test_token",
            "user_id": str(uuid4()),
            "user_role": "applicant",
            "language": "ru",
            "state": state,
        }

        # Import handler
        from app.routers.common import cmd_start

        # Execute handler
        await cmd_start(message, user_role="applicant", language="ru", state=state)

        # Verify
        message.answer.assert_called_once()
        state.clear.assert_called_once()

        # Verify welcome message was sent
        call_args = message.answer.call_args
        assert "Добро пожаловать" in call_args[1]["text"]

    async def test_help_command_handler(self, bot, dispatcher, storage):
        """Test /help command handler"""
        # Mock message
        message = MagicMock(spec=types.Message)
        message.from_user = MagicMock()
        message.from_user.id = 123456789
        message.text = "/help"
        message.answer = AsyncMock()

        # Import handler
        from app.routers.common import cmd_help

        # Execute handler
        await cmd_help(message, language="ru")

        # Verify
        message.answer.assert_called_once()

        # Verify help text was sent
        call_args = message.answer.call_args
        assert "Команды" in call_args[1]["text"] or "помощь" in call_args[1]["text"].lower()

    async def test_menu_command_handler(self, bot, dispatcher, storage):
        """Test /menu command handler"""
        # Mock message
        message = MagicMock(spec=types.Message)
        message.from_user = MagicMock()
        message.from_user.id = 123456789
        message.text = "/menu"
        message.answer = AsyncMock()

        # Mock FSM context
        state = MagicMock(spec=FSMContext)
        state.clear = AsyncMock()

        # Import handler
        from app.routers.common import cmd_menu

        # Execute handler
        await cmd_menu(message, user_role="applicant", language="ru", state=state)

        # Verify
        message.answer.assert_called_once()
        state.clear.assert_called_once()

    async def test_language_command_handler(self, bot, dispatcher, storage):
        """Test /language command handler"""
        # Mock message
        message = MagicMock(spec=types.Message)
        message.from_user = MagicMock()
        message.from_user.id = 123456789
        message.text = "/language"
        message.answer = AsyncMock()

        # Import handler
        from app.routers.common import cmd_language

        # Execute handler
        await cmd_language(message, language="ru")

        # Verify
        message.answer.assert_called_once()

        # Verify language selection keyboard was sent
        call_args = message.answer.call_args
        assert "reply_markup" in call_args[1]


@pytest.mark.asyncio
class TestRequestHandlers:
    """Test cases for request management handlers"""

    async def test_create_request_button_handler(
        self, bot, dispatcher, storage
    ):
        """Test 'Create Request' button handler"""
        # Mock message
        message = MagicMock(spec=types.Message)
        message.from_user = MagicMock()
        message.from_user.id = 123456789
        message.text = "➕ Создать заявку"
        message.answer = AsyncMock()

        # Mock FSM context
        state = MagicMock(spec=FSMContext)
        state.set_state = AsyncMock()

        # Import handler
        from app.routers.requests import button_create_request

        # Execute handler
        await button_create_request(message, state=state, language="ru")

        # Verify
        message.answer.assert_called_once()
        state.set_state.assert_called_once_with(RequestCreationStates.waiting_for_building)

        # Verify prompt was sent
        call_args = message.answer.call_args
        assert "дом" in call_args[1]["text"].lower()

    async def test_create_request_building_input(
        self, bot, dispatcher, storage
    ):
        """Test building input in request creation flow"""
        # Mock message
        message = MagicMock(spec=types.Message)
        message.from_user = MagicMock()
        message.from_user.id = 123456789
        message.text = "5"
        message.answer = AsyncMock()

        # Mock FSM context
        state = MagicMock(spec=FSMContext)
        state.update_data = AsyncMock()
        state.set_state = AsyncMock()

        # Import handler
        from app.routers.requests import process_building_input

        # Execute handler
        await process_building_input(message, state=state, language="ru")

        # Verify
        message.answer.assert_called_once()
        state.update_data.assert_called_once_with(building="5")
        state.set_state.assert_called_once_with(RequestCreationStates.waiting_for_apartment)

    async def test_create_request_apartment_input(
        self, bot, dispatcher, storage
    ):
        """Test apartment input in request creation flow"""
        # Mock message
        message = MagicMock(spec=types.Message)
        message.from_user = MagicMock()
        message.from_user.id = 123456789
        message.text = "42"
        message.answer = AsyncMock()

        # Mock FSM context
        state = MagicMock(spec=FSMContext)
        state.update_data = AsyncMock()
        state.set_state = AsyncMock()

        # Import handler
        from app.routers.requests import process_apartment_input

        # Execute handler
        await process_apartment_input(message, state=state, language="ru")

        # Verify
        message.answer.assert_called_once()
        state.update_data.assert_called_once_with(apartment="42")
        state.set_state.assert_called_once_with(RequestCreationStates.waiting_for_description)

    async def test_create_request_description_input(
        self, bot, dispatcher, storage, httpx_mock
    ):
        """Test description input and request creation"""
        # Mock message
        message = MagicMock(spec=types.Message)
        message.from_user = MagicMock()
        message.from_user.id = 123456789
        message.text = "Течет кран на кухне"
        message.answer = AsyncMock()

        # Mock FSM context with stored data
        state = MagicMock(spec=FSMContext)
        state.get_data = AsyncMock(
            return_value={"building": "5", "apartment": "42"}
        )
        state.clear = AsyncMock()

        # Mock Request Service response
        mock_response = {
            "request_number": "250101-001",
            "building": "5",
            "apartment": "42",
            "description": "Течет кран на кухне",
            "status": "new",
        }

        # Import handler
        from app.routers.requests import process_description_input

        # Mock request service client
        with patch("app.integrations.request_client.RequestServiceClient.create_request") as mock_create:
            mock_create.return_value = mock_response

            # Execute handler
            await process_description_input(
                message, state=state, token="test_token"
            )

            # Verify
            message.answer.assert_called_once()
            state.clear.assert_called_once()

            # Verify request was created via service
            mock_create.assert_called_once()

            # Verify success message includes request number
            call_args = message.answer.call_args
            assert "250101-001" in call_args[1]["text"]

    async def test_my_requests_button_handler(
        self, bot, dispatcher, storage, httpx_mock
    ):
        """Test 'My Requests' button handler"""
        # Mock message
        message = MagicMock(spec=types.Message)
        message.from_user = MagicMock()
        message.from_user.id = 123456789
        message.text = "📋 Мои заявки"
        message.answer = AsyncMock()

        # Mock Request Service response
        mock_response = {
            "items": [
                {
                    "request_number": "250101-001",
                    "building": "5",
                    "apartment": "42",
                    "status": "new",
                    "description": "Test request 1",
                },
                {
                    "request_number": "250101-002",
                    "building": "3",
                    "apartment": "15",
                    "status": "in_progress",
                    "description": "Test request 2",
                },
            ],
            "total": 2,
        }

        # Import handler
        from app.routers.requests import button_my_requests

        # Mock request service client
        with patch("app.integrations.request_client.RequestServiceClient.get_my_requests") as mock_get:
            mock_get.return_value = mock_response

            # Execute handler
            await button_my_requests(message, token="test_token", language="ru")

            # Verify
            message.answer.assert_called()

            # Verify requests were retrieved
            mock_get.assert_called_once()

            # Verify both requests were displayed
            call_args_list = message.answer.call_args_list
            messages_sent = "".join([str(call[1].get("text", "")) for call in call_args_list])
            assert "250101-001" in messages_sent
            assert "250101-002" in messages_sent

    async def test_callback_view_request(
        self, bot, dispatcher, storage, httpx_mock
    ):
        """Test callback query for viewing request details"""
        # Mock callback query
        callback = MagicMock(spec=types.CallbackQuery)
        callback.from_user = MagicMock()
        callback.from_user.id = 123456789
        callback.data = "request:view:250101-001"
        callback.message = MagicMock()
        callback.message.answer = AsyncMock()
        callback.answer = AsyncMock()

        # Mock Request Service response
        mock_response = {
            "request_number": "250101-001",
            "building": "5",
            "apartment": "42",
            "description": "Detailed description",
            "status": "in_progress",
            "priority": "high",
            "executor_id": str(uuid4()),
        }

        # Import handler
        from app.routers.requests import callback_request_action

        # Mock request service client
        with patch("app.integrations.request_client.RequestServiceClient.get_request_by_number") as mock_get:
            mock_get.return_value = mock_response

            # Execute handler
            await callback_request_action(callback, token="test_token", language="ru")

            # Verify
            callback.message.answer.assert_called()
            callback.answer.assert_called_once()

            # Verify request details were retrieved and displayed
            mock_get.assert_called_once_with("250101-001", token="test_token")

    async def test_callback_take_request(
        self, bot, dispatcher, storage, httpx_mock
    ):
        """Test callback query for taking a request"""
        # Mock callback query
        callback = MagicMock(spec=types.CallbackQuery)
        callback.from_user = MagicMock()
        callback.from_user.id = 123456789
        callback.data = "request:take:250101-001"
        callback.message = MagicMock()
        callback.message.answer = AsyncMock()
        callback.answer = AsyncMock()

        # Mock Request Service response
        mock_response = {
            "request_number": "250101-001",
            "status": "assigned",
            "executor_id": str(uuid4()),
        }

        # Import handler
        from app.routers.requests import callback_request_action

        # Mock request service client
        with patch("app.integrations.request_client.RequestServiceClient.take_request") as mock_take:
            mock_take.return_value = mock_response

            # Execute handler (with executor role)
            await callback_request_action(
                callback, token="test_token", language="ru", user_role="executor"
            )

            # Verify
            callback.answer.assert_called()

            # Verify request was taken via service
            mock_take.assert_called_once_with("250101-001", token="test_token")

    async def test_cancel_button_handler(
        self, bot, dispatcher, storage
    ):
        """Test 'Cancel' button handler during FSM flow"""
        # Mock message
        message = MagicMock(spec=types.Message)
        message.from_user = MagicMock()
        message.from_user.id = 123456789
        message.text = "❌ Отмена"
        message.answer = AsyncMock()

        # Mock FSM context
        state = MagicMock(spec=FSMContext)
        state.clear = AsyncMock()

        # Import handler
        from app.routers.requests import button_cancel

        # Execute handler
        await button_cancel(message, state=state, user_role="applicant", language="ru")

        # Verify
        message.answer.assert_called_once()
        state.clear.assert_called_once()

        # Verify cancellation message was sent
        call_args = message.answer.call_args
        assert "отмен" in call_args[1]["text"].lower()
