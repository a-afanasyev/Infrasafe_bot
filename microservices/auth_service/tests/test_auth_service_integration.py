# Integration Tests for Auth Service
# UK Management Bot - Auth Service

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from services.auth_service import AuthService
from models.auth import Base
from config import settings

# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_auth_integration.db"

# Mock User Service responses
MOCK_USER_DATA = {
    "id": 1,
    "user_id": 1,
    "telegram_id": 123456789,
    "username": "test_user",
    "first_name": "Test",
    "last_name": "User",
    "phone": "+1234567890",
    "email": "test@example.com",
    "language_code": "en",
    "status": "approved",
    "is_active": True,
    "roles": ["user"],
    "is_verified": True
}

@pytest.fixture
async def async_session():
    """Create async test database session"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_factory = async_sessionmaker(engine, class_=AsyncSession)

    async with async_session_factory() as session:
        yield session

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()

@pytest.fixture
async def auth_service(async_session):
    """Create auth service instance with mocked User Service"""
    service = AuthService(async_session)
    return service

class TestAuthServiceIntegration:
    """Integration tests for AuthService with credential management"""

    @pytest.mark.asyncio
    async def test_production_mode_no_fallback(self, auth_service):
        """Test that fallback is disabled in production mode"""
        # Mock settings to simulate production
        with patch.object(settings, 'debug', False):
            # Mock failed User Service call
            with patch('httpx.AsyncClient.get') as mock_get:
                mock_response = AsyncMock()
                mock_response.status_code = 500
                mock_response.text = "Internal Server Error"
                mock_get.return_value.__aenter__.return_value.get.return_value = mock_response

                # Should return None in production, not fallback data
                user_data = await auth_service._get_user_from_user_service("123456789")
                assert user_data is None

    @pytest.mark.asyncio
    async def test_development_mode_with_fallback(self, auth_service):
        """Test that fallback works in development mode"""
        # Mock settings to simulate development
        with patch.object(settings, 'debug', True):
            # Mock failed User Service call
            with patch('httpx.AsyncClient.get') as mock_get:
                mock_response = AsyncMock()
                mock_response.status_code = 500
                mock_response.text = "Internal Server Error"
                mock_get.return_value.__aenter__.return_value.get.return_value = mock_response

                # Should return fallback data in development
                user_data = await auth_service._get_user_from_user_service("123456789")
                assert user_data is not None
                assert user_data["telegram_id"] == "123456789"
                assert user_data["username"] == "admin"

    @pytest.mark.asyncio
    async def test_successful_user_service_call(self, auth_service):
        """Test successful User Service API call"""
        # Mock successful User Service response
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = MOCK_USER_DATA
            mock_get.return_value.__aenter__.return_value.get.return_value = mock_response

            user_data = await auth_service._get_user_from_user_service("123456789")

            assert user_data is not None
            assert user_data["user_id"] == 1
            assert user_data["telegram_id"] == "123456789"
            assert user_data["username"] == "test_user"

    @pytest.mark.asyncio
    async def test_password_authentication_flow(self, auth_service, async_session):
        """Test complete password authentication flow"""
        telegram_id = "123456789"
        password = "test_password_123"

        # Mock User Service response
        with patch.object(auth_service, '_get_user_from_user_service') as mock_user_service:
            mock_user_service.return_value = MOCK_USER_DATA

            # First authentication - should create credentials
            auth_result = await auth_service.authenticate_with_password(
                telegram_id=telegram_id,
                password=password,
                ip_address="127.0.0.1"
            )

            # Should fail because no password is set yet
            assert auth_result["success"] == False
            assert auth_result["error"] == "password_not_set"

            # Set password for user
            password_set = await auth_service.set_user_password(telegram_id, password)
            assert password_set == True

            # Now authentication should succeed
            auth_result = await auth_service.authenticate_with_password(
                telegram_id=telegram_id,
                password=password,
                ip_address="127.0.0.1"
            )

            assert auth_result["success"] == True
            assert "user_data" in auth_result
            assert auth_result["user_data"]["user_id"] == 1

            # Test wrong password
            auth_result = await auth_service.authenticate_with_password(
                telegram_id=telegram_id,
                password="wrong_password",
                ip_address="127.0.0.1"
            )

            assert auth_result["success"] == False
            assert auth_result["error"] == "invalid_password"

    @pytest.mark.asyncio
    async def test_mfa_flow(self, auth_service, async_session):
        """Test MFA setup and verification flow"""
        telegram_id = "987654321"

        # Mock User Service response
        with patch.object(auth_service, '_get_user_from_user_service') as mock_user_service:
            mock_user_service.return_value = {
                **MOCK_USER_DATA,
                "telegram_id": int(telegram_id),
                "user_id": 2
            }

            # Enable MFA
            mfa_result = await auth_service.enable_mfa_for_user(telegram_id)
            assert mfa_result["success"] == True
            assert "secret" in mfa_result
            assert "backup_codes" in mfa_result

            # Test backup code verification
            backup_code = mfa_result["backup_codes"][0]
            is_valid = await auth_service.verify_mfa_token(telegram_id, backup_code)
            assert is_valid == True

            # Same backup code should not work twice
            is_valid = await auth_service.verify_mfa_token(telegram_id, backup_code)
            assert is_valid == False

    @pytest.mark.asyncio
    async def test_user_not_found_handling(self, auth_service):
        """Test handling when user is not found in User Service"""
        # Mock User Service returning 404
        with patch('httpx.AsyncClient.get') as mock_get:
            mock_response = AsyncMock()
            mock_response.status_code = 404
            mock_get.return_value.__aenter__.return_value.get.return_value = mock_response

            # Authentication should fail
            auth_result = await auth_service.authenticate_with_password(
                telegram_id="999999999",
                password="any_password"
            )

            assert auth_result["success"] == False
            assert auth_result["error"] == "user_not_found"

            # Setting password should fail
            password_set = await auth_service.set_user_password("999999999", "password")
            assert password_set == False

    @pytest.mark.asyncio
    async def test_service_token_validation(self, auth_service):
        """Test service token validation"""
        # Test valid JWT token (mocked)
        with patch('services.service_token.service_token_manager.validate_service_token') as mock_validate:
            mock_validate.return_value = {
                "service_name": "test-service",
                "permissions": ["read", "write"],
                "token_type": "jwt"
            }

            result = await auth_service.validate_service_token("valid_jwt_token")
            assert result is not None
            assert result["service_name"] == "test-service"

        # Test invalid token
        with patch('services.service_token.service_token_manager.validate_service_token') as mock_validate:
            mock_validate.return_value = None

            with patch('services.service_token.service_token_manager.validate_api_key') as mock_api_key:
                mock_api_key.return_value = None

                result = await auth_service.validate_service_token("invalid_token")
                assert result is None

    @pytest.mark.asyncio
    async def test_concurrent_authentication_attempts(self, auth_service, async_session):
        """Test concurrent authentication attempts"""
        telegram_id = "555666777"
        password = "concurrent_test_password"

        # Mock User Service response
        with patch.object(auth_service, '_get_user_from_user_service') as mock_user_service:
            mock_user_service.return_value = {
                **MOCK_USER_DATA,
                "telegram_id": int(telegram_id),
                "user_id": 3
            }

            # Set password
            await auth_service.set_user_password(telegram_id, password)

            # Simulate concurrent authentication attempts
            tasks = []
            for i in range(5):
                task = auth_service.authenticate_with_password(
                    telegram_id=telegram_id,
                    password=password,
                    ip_address=f"127.0.0.{i}"
                )
                tasks.append(task)

            results = await asyncio.gather(*tasks)

            # All should succeed
            for result in results:
                assert result["success"] == True

    @pytest.mark.asyncio
    async def test_error_handling_and_logging(self, auth_service, async_session):
        """Test error handling and audit logging"""
        telegram_id = "error_test_user"

        # Test with service that raises exception
        with patch.object(auth_service, '_get_user_from_user_service') as mock_user_service:
            mock_user_service.side_effect = Exception("Network error")

            auth_result = await auth_service.authenticate_with_password(
                telegram_id=telegram_id,
                password="any_password"
            )

            assert auth_result["success"] == False
            assert auth_result["error"] == "authentication_failed"

# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])