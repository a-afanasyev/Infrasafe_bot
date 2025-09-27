# Tests for Credential Service
# UK Management Bot - Auth Service

import pytest
import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

from services.credential_service import CredentialService
from models.auth import Base, UserCredential, AuthLog
from config import settings

# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_auth.db"

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
async def credential_service(async_session):
    """Create credential service instance"""
    return CredentialService(async_session)

class TestCredentialService:
    """Test suite for CredentialService"""

    @pytest.mark.asyncio
    async def test_create_user_credentials(self, credential_service, async_session):
        """Test creating new user credentials"""
        user_id = 123
        telegram_id = "123456789"

        # Create credentials
        credentials = await credential_service.create_user_credentials(
            user_id=user_id,
            telegram_id=telegram_id
        )

        assert credentials.user_id == user_id
        assert credentials.telegram_id == telegram_id
        assert credentials.failed_attempts == 0
        assert credentials.mfa_enabled == False
        assert credentials.password_hash is None  # No password set yet

        await async_session.commit()

    @pytest.mark.asyncio
    async def test_set_and_verify_password(self, credential_service, async_session):
        """Test setting and verifying passwords"""
        user_id = 456
        telegram_id = "456789123"
        password = "test_password_123"

        # Create credentials first
        credentials = await credential_service.create_user_credentials(
            user_id=user_id,
            telegram_id=telegram_id
        )
        await async_session.commit()

        # Set password
        result = await credential_service.set_password(user_id, password)
        assert result == True

        # Verify correct password
        auth_result = await credential_service.verify_password(user_id, password)
        assert auth_result["success"] == True
        assert auth_result["mfa_required"] == False

        # Verify incorrect password
        auth_result = await credential_service.verify_password(user_id, "wrong_password")
        assert auth_result["success"] == False
        assert auth_result["error"] == "invalid_password"

    @pytest.mark.asyncio
    async def test_account_lockout(self, credential_service, async_session):
        """Test account lockout after failed attempts"""
        user_id = 789
        telegram_id = "789123456"
        password = "correct_password"

        # Create credentials and set password
        await credential_service.create_user_credentials(user_id, telegram_id)
        await credential_service.set_password(user_id, password)
        await async_session.commit()

        # Make multiple failed attempts
        max_attempts = settings.max_login_attempts
        for i in range(max_attempts):
            result = await credential_service.verify_password(user_id, "wrong_password")
            assert result["success"] == False

            if i < max_attempts - 1:
                assert "attempts_remaining" in result
                assert result["attempts_remaining"] == max_attempts - i - 1

        # Account should be locked now
        result = await credential_service.verify_password(user_id, "wrong_password")
        assert result["success"] == False
        assert result["error"] == "account_locked"

        # Even correct password should fail when locked
        result = await credential_service.verify_password(user_id, password)
        assert result["success"] == False
        assert result["error"] == "account_locked"

    @pytest.mark.asyncio
    async def test_mfa_setup_and_verification(self, credential_service, async_session):
        """Test MFA setup and token verification"""
        user_id = 999
        telegram_id = "999888777"

        # Create credentials
        await credential_service.create_user_credentials(user_id, telegram_id)
        await async_session.commit()

        # Enable MFA
        mfa_result = await credential_service.enable_mfa(user_id)
        assert mfa_result["success"] == True
        assert "secret" in mfa_result
        assert "backup_codes" in mfa_result
        assert len(mfa_result["backup_codes"]) == 10

        # Test backup code verification
        backup_code = mfa_result["backup_codes"][0]
        is_valid = await credential_service.verify_mfa_token(user_id, backup_code)
        assert is_valid == True

        # Same backup code should not work twice
        is_valid = await credential_service.verify_mfa_token(user_id, backup_code)
        assert is_valid == False

    @pytest.mark.asyncio
    async def test_get_credentials_by_telegram_id(self, credential_service, async_session):
        """Test retrieving credentials by telegram ID"""
        user_id = 111
        telegram_id = "111222333"

        # Create credentials
        await credential_service.create_user_credentials(user_id, telegram_id)
        await async_session.commit()

        # Retrieve by telegram_id
        credentials = await credential_service.get_credentials_by_telegram_id(telegram_id)
        assert credentials is not None
        assert credentials.user_id == user_id
        assert credentials.telegram_id == telegram_id

        # Test non-existent telegram_id
        credentials = await credential_service.get_credentials_by_telegram_id("999999999")
        assert credentials is None

    @pytest.mark.asyncio
    async def test_password_validation(self, credential_service, async_session):
        """Test password validation rules"""
        user_id = 222
        telegram_id = "222333444"

        # Create credentials
        await credential_service.create_user_credentials(user_id, telegram_id)
        await async_session.commit()

        # Test password too short
        with pytest.raises(ValueError, match="Password must be at least"):
            await credential_service.set_password(user_id, "123")

        # Test valid password
        result = await credential_service.set_password(user_id, "valid_password_123")
        assert result == True

    @pytest.mark.asyncio
    async def test_cleanup_expired_locks(self, credential_service, async_session):
        """Test cleanup of expired account locks"""
        user_id = 333
        telegram_id = "333444555"

        # Create credentials
        credentials = await credential_service.create_user_credentials(user_id, telegram_id)
        await async_session.commit()

        # Manually set expired lock
        credentials.locked_until = datetime.utcnow() - timedelta(minutes=5)  # 5 minutes ago
        credentials.failed_attempts = 3
        await async_session.commit()

        # Cleanup expired locks
        await credential_service.cleanup_expired_locks()

        # Refresh credentials
        await async_session.refresh(credentials)

        assert credentials.locked_until is None
        assert credentials.failed_attempts == 0

    @pytest.mark.asyncio
    async def test_duplicate_credentials_prevention(self, credential_service, async_session):
        """Test prevention of duplicate credentials"""
        user_id = 444
        telegram_id = "444555666"

        # Create first credentials
        await credential_service.create_user_credentials(user_id, telegram_id)
        await async_session.commit()

        # Try to create duplicate
        with pytest.raises(ValueError, match="already exist"):
            await credential_service.create_user_credentials(user_id, telegram_id)

    @pytest.mark.asyncio
    async def test_auth_logging(self, credential_service, async_session):
        """Test authentication event logging"""
        user_id = 555
        telegram_id = "555666777"
        password = "test_password"

        # Create credentials and set password
        await credential_service.create_user_credentials(user_id, telegram_id)
        await credential_service.set_password(user_id, password)
        await async_session.commit()

        # Perform authentication (should log event)
        await credential_service.verify_password(user_id, password, ip_address="127.0.0.1")

        # Check if auth log was created
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM auth_logs WHERE user_id = :user_id"),
            {"user_id": user_id}
        )
        log_count = result.scalar()
        assert log_count > 0

# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])