"""
Bot Gateway Service - Service Client Tests
UK Management Bot

Tests for HTTP service clients (Auth, User, Request services).
"""

import pytest
from uuid import uuid4
import httpx
from pytest_httpx import HTTPXMock

from app.integrations.auth_client import AuthServiceClient
from app.integrations.user_client import UserServiceClient
from app.integrations.request_client import RequestServiceClient
from app.integrations.base_client import BaseServiceClient


@pytest.mark.asyncio
class TestAuthServiceClient:
    """Test cases for Auth Service Client"""

    async def test_login_telegram_success(self, httpx_mock: HTTPXMock):
        """Test successful Telegram login"""
        client = AuthServiceClient(base_url="http://test.local")

        # Mock Auth Service response
        mock_response = {
            "access_token": "test_jwt_token",
            "token_type": "bearer",
            "expires_in": 3600,
            "user_id": str(uuid4()),
            "role": "applicant",
        }

        httpx_mock.add_response(
            method="POST",
            url="http://test.local/api/v1/auth/telegram/login",
            json=mock_response,
            status_code=200,
        )

        # Execute
        result = await client.login_telegram(
            telegram_id=123456789, first_name="Test", last_name="User"
        )

        # Verify
        assert result["access_token"] == "test_jwt_token"
        assert result["user_id"] == mock_response["user_id"]
        assert result["role"] == "applicant"

        await client.close()

    async def test_login_telegram_failure(self, httpx_mock: HTTPXMock):
        """Test failed Telegram login"""
        client = AuthServiceClient(base_url="http://test.local")

        # Mock Auth Service error
        httpx_mock.add_response(
            method="POST",
            url="http://test.local/api/v1/auth/telegram/login",
            json={"error": "User not found"},
            status_code=404,
        )

        # Execute - should raise exception
        with pytest.raises(httpx.HTTPStatusError):
            await client.login_telegram(telegram_id=999999999)

        await client.close()

    async def test_verify_token_success(self, httpx_mock: HTTPXMock):
        """Test successful token verification"""
        client = AuthServiceClient(base_url="http://test.local")

        mock_response = {
            "valid": True,
            "user_id": str(uuid4()),
            "role": "executor",
            "permissions": ["request:create", "request:view"],
        }

        httpx_mock.add_response(
            method="POST",
            url="http://test.local/api/v1/auth/verify",
            json=mock_response,
            status_code=200,
        )

        # Execute
        result = await client.verify_token("test_token")

        # Verify
        assert result["valid"] is True
        assert result["role"] == "executor"

        await client.close()

    async def test_verify_token_expired(self, httpx_mock: HTTPXMock):
        """Test expired token verification"""
        client = AuthServiceClient(base_url="http://test.local")

        httpx_mock.add_response(
            method="POST",
            url="http://test.local/api/v1/auth/verify",
            json={"valid": False, "error": "Token expired"},
            status_code=401,
        )

        # Execute - should raise exception
        with pytest.raises(httpx.HTTPStatusError):
            await client.verify_token("expired_token")

        await client.close()


@pytest.mark.asyncio
class TestUserServiceClient:
    """Test cases for User Service Client"""

    async def test_get_by_telegram_id_success(self, httpx_mock: HTTPXMock):
        """Test successful user lookup by Telegram ID"""
        client = UserServiceClient(base_url="http://test.local")

        user_id = uuid4()
        mock_response = {
            "id": str(user_id),
            "telegram_id": 123456789,
            "role": "applicant",
            "first_name": "Test",
            "last_name": "User",
            "phone": "+998901234567",
            "language": "ru",
            "is_active": True,
        }

        httpx_mock.add_response(
            method="GET",
            url="http://test.local/api/v1/users/telegram/123456789",
            json=mock_response,
            status_code=200,
        )

        # Execute
        result = await client.get_by_telegram_id(123456789, token="test_token")

        # Verify
        assert result["id"] == str(user_id)
        assert result["telegram_id"] == 123456789
        assert result["role"] == "applicant"

        await client.close()

    async def test_get_by_telegram_id_not_found(self, httpx_mock: HTTPXMock):
        """Test user not found"""
        client = UserServiceClient(base_url="http://test.local")

        httpx_mock.add_response(
            method="GET",
            url="http://test.local/api/v1/users/telegram/999999999",
            json={"error": "User not found"},
            status_code=404,
        )

        # Execute - should raise exception
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_by_telegram_id(999999999, token="test_token")

        await client.close()

    async def test_update_user_success(self, httpx_mock: HTTPXMock):
        """Test successful user update"""
        client = UserServiceClient(base_url="http://test.local")

        user_id = uuid4()
        mock_response = {
            "id": str(user_id),
            "telegram_id": 123456789,
            "language": "uz",  # Updated language
            "is_active": True,
        }

        httpx_mock.add_response(
            method="PATCH",
            url=f"http://test.local/api/v1/users/{user_id}",
            json=mock_response,
            status_code=200,
        )

        # Execute
        result = await client.update_user(
            user_id=user_id, data={"language": "uz"}, token="test_token"
        )

        # Verify
        assert result["language"] == "uz"

        await client.close()


@pytest.mark.asyncio
class TestRequestServiceClient:
    """Test cases for Request Service Client"""

    async def test_create_request_success(self, httpx_mock: HTTPXMock):
        """Test successful request creation"""
        client = RequestServiceClient(base_url="http://test.local")

        mock_response = {
            "request_number": "250101-001",
            "building": "1",
            "apartment": "101",
            "description": "Test request",
            "status": "new",
            "priority": "normal",
            "created_by": str(uuid4()),
        }

        httpx_mock.add_response(
            method="POST",
            url="http://test.local/api/v1/requests",
            json=mock_response,
            status_code=201,
        )

        # Execute
        result = await client.create_request(
            data={
                "building": "1",
                "apartment": "101",
                "description": "Test request",
            },
            token="test_token",
        )

        # Verify
        assert result["request_number"] == "250101-001"
        assert result["status"] == "new"

        await client.close()

    async def test_get_my_requests_success(self, httpx_mock: HTTPXMock):
        """Test successful retrieval of user's requests"""
        client = RequestServiceClient(base_url="http://test.local")

        mock_response = {
            "items": [
                {
                    "request_number": "250101-001",
                    "building": "1",
                    "apartment": "101",
                    "status": "new",
                },
                {
                    "request_number": "250101-002",
                    "building": "2",
                    "apartment": "202",
                    "status": "in_progress",
                },
            ],
            "total": 2,
            "limit": 10,
            "offset": 0,
        }

        httpx_mock.add_response(
            method="GET",
            url="http://test.local/api/v1/requests/my",
            json=mock_response,
            status_code=200,
        )

        # Execute
        result = await client.get_my_requests(token="test_token")

        # Verify
        assert len(result["items"]) == 2
        assert result["total"] == 2

        await client.close()

    async def test_get_my_requests_with_filters(self, httpx_mock: HTTPXMock):
        """Test retrieval with filters"""
        client = RequestServiceClient(base_url="http://test.local")

        mock_response = {
            "items": [
                {
                    "request_number": "250101-001",
                    "status": "new",
                }
            ],
            "total": 1,
        }

        httpx_mock.add_response(
            method="GET",
            url="http://test.local/api/v1/requests/my?status=new&limit=5&offset=0",
            json=mock_response,
            status_code=200,
        )

        # Execute
        result = await client.get_my_requests(
            token="test_token", status="new", limit=5, offset=0
        )

        # Verify
        assert len(result["items"]) == 1
        assert result["items"][0]["status"] == "new"

        await client.close()

    async def test_get_request_by_number_success(self, httpx_mock: HTTPXMock):
        """Test successful request lookup by number"""
        client = RequestServiceClient(base_url="http://test.local")

        mock_response = {
            "request_number": "250101-001",
            "building": "1",
            "apartment": "101",
            "description": "Detailed request info",
            "status": "in_progress",
            "executor_id": str(uuid4()),
        }

        httpx_mock.add_response(
            method="GET",
            url="http://test.local/api/v1/requests/250101-001",
            json=mock_response,
            status_code=200,
        )

        # Execute
        result = await client.get_request_by_number("250101-001", token="test_token")

        # Verify
        assert result["request_number"] == "250101-001"
        assert result["status"] == "in_progress"

        await client.close()

    async def test_take_request_success(self, httpx_mock: HTTPXMock):
        """Test successfully taking a request"""
        client = RequestServiceClient(base_url="http://test.local")

        mock_response = {
            "request_number": "250101-001",
            "status": "assigned",
            "executor_id": str(uuid4()),
        }

        httpx_mock.add_response(
            method="POST",
            url="http://test.local/api/v1/requests/250101-001/take",
            json=mock_response,
            status_code=200,
        )

        # Execute
        result = await client.take_request("250101-001", token="test_token")

        # Verify
        assert result["status"] == "assigned"

        await client.close()

    async def test_add_comment_success(self, httpx_mock: HTTPXMock):
        """Test successfully adding a comment"""
        client = RequestServiceClient(base_url="http://test.local")

        mock_response = {
            "id": str(uuid4()),
            "request_number": "250101-001",
            "comment_text": "Test comment",
            "author_id": str(uuid4()),
        }

        httpx_mock.add_response(
            method="POST",
            url="http://test.local/api/v1/requests/250101-001/comments",
            json=mock_response,
            status_code=201,
        )

        # Execute
        result = await client.add_comment(
            request_number="250101-001",
            comment_text="Test comment",
            token="test_token",
        )

        # Verify
        assert result["comment_text"] == "Test comment"

        await client.close()


@pytest.mark.asyncio
class TestBaseServiceClient:
    """Test cases for Base Service Client"""

    async def test_request_with_automatic_retry(self, httpx_mock: HTTPXMock):
        """Test automatic retry on timeout"""
        client = BaseServiceClient(base_url="http://test.local", service_name="test")

        # First attempt times out, second succeeds
        httpx_mock.add_exception(
            httpx.TimeoutException("Request timeout"), method="GET", url="http://test.local/test"
        )
        httpx_mock.add_response(
            method="GET", url="http://test.local/test", json={"success": True}, status_code=200
        )

        # Execute - should retry automatically
        response = await client._request("GET", "/test")

        # Verify
        assert response.status_code == 200
        assert response.json()["success"] is True

        await client.close()

    async def test_request_includes_jwt_token(self, httpx_mock: HTTPXMock):
        """Test that requests include JWT token in headers"""
        client = BaseServiceClient(base_url="http://test.local", service_name="test")

        httpx_mock.add_response(
            method="GET",
            url="http://test.local/test",
            json={"success": True},
            status_code=200,
            match_headers={"Authorization": "Bearer test_token"},
        )

        # Execute
        response = await client._request("GET", "/test", token="test_token")

        # Verify
        assert response.status_code == 200

        await client.close()

    async def test_request_handles_json_data(self, httpx_mock: HTTPXMock):
        """Test that requests correctly serialize JSON data"""
        client = BaseServiceClient(base_url="http://test.local", service_name="test")

        def match_json(request: httpx.Request):
            data = request.read()
            import json

            payload = json.loads(data)
            return payload.get("key") == "value"

        httpx_mock.add_response(
            method="POST",
            url="http://test.local/test",
            json={"success": True},
            status_code=200,
            match_content=match_json,
        )

        # Execute
        response = await client._request("POST", "/test", json_data={"key": "value"})

        # Verify
        assert response.status_code == 200

        await client.close()

    async def test_request_max_retries_exceeded(self, httpx_mock: HTTPXMock):
        """Test that request fails after max retries"""
        client = BaseServiceClient(base_url="http://test.local", service_name="test")

        # All attempts time out
        for _ in range(4):  # Initial + 3 retries
            httpx_mock.add_exception(
                httpx.TimeoutException("Request timeout"),
                method="GET",
                url="http://test.local/test",
            )

        # Execute - should raise after all retries
        with pytest.raises(httpx.TimeoutException):
            await client._request("GET", "/test")

        await client.close()
