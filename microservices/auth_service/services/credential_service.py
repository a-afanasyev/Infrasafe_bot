# Password and Credential Management Service
# UK Management Bot - Auth Service

import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import bcrypt
import pyotp

from models.auth import UserCredential, AuthLog
from config import settings

logger = logging.getLogger(__name__)

class CredentialService:
    """Service for managing user credentials and password authentication"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_user_credentials(self, user_id: int, telegram_id: str, password: str = None) -> UserCredential:
        """Create new user credentials"""
        try:
            # Check if credentials already exist
            existing = await self.get_credentials_by_user_id(user_id)
            if existing:
                raise ValueError(f"Credentials for user {user_id} already exist")

            # Create new credentials
            credentials = UserCredential(
                user_id=user_id,
                telegram_id=str(telegram_id),
                failed_attempts=0,
                mfa_enabled=False,
                remember_device=False,
                session_timeout_minutes=settings.jwt_expire_minutes,
                created_at=datetime.utcnow()
            )

            # Set password if provided
            if password:
                await self._set_password(credentials, password)

            self.db.add(credentials)
            await self.db.flush()

            logger.info(f"Created credentials for user {user_id}")
            return credentials

        except Exception as e:
            logger.error(f"Error creating credentials for user {user_id}: {e}")
            raise

    async def get_credentials_by_user_id(self, user_id: int) -> Optional[UserCredential]:
        """Get user credentials by user ID"""
        try:
            result = await self.db.execute(
                select(UserCredential).where(UserCredential.user_id == user_id)
            )
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"Error getting credentials for user {user_id}: {e}")
            return None

    async def get_credentials_by_telegram_id(self, telegram_id: str) -> Optional[UserCredential]:
        """Get user credentials by Telegram ID"""
        try:
            result = await self.db.execute(
                select(UserCredential).where(UserCredential.telegram_id == str(telegram_id))
            )
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"Error getting credentials for telegram_id {telegram_id}: {e}")
            return None

    async def set_password(self, user_id: int, password: str, force_change: bool = False) -> bool:
        """Set or update user password"""
        try:
            credentials = await self.get_credentials_by_user_id(user_id)
            if not credentials:
                raise ValueError(f"Credentials not found for user {user_id}")

            await self._set_password(credentials, password)
            credentials.force_password_change = force_change
            credentials.last_password_change = datetime.utcnow()
            credentials.failed_attempts = 0  # Reset failed attempts
            credentials.locked_until = None  # Unlock account

            await self.db.commit()

            logger.info(f"Password updated for user {user_id}")
            return True

        except Exception as e:
            logger.error(f"Error setting password for user {user_id}: {e}")
            await self.db.rollback()
            return False

    async def verify_password(self, user_id: int, password: str, ip_address: str = None) -> Dict[str, Any]:
        """Verify user password and handle security policies"""
        try:
            credentials = await self.get_credentials_by_user_id(user_id)
            if not credentials:
                await self._log_auth_event(
                    user_id=user_id,
                    event_type="login_attempt",
                    event_status="failure",
                    event_message="Credentials not found",
                    ip_address=ip_address
                )
                return {"success": False, "error": "invalid_credentials"}

            # Check if account is locked
            if credentials.locked_until and credentials.locked_until > datetime.utcnow():
                await self._log_auth_event(
                    user_id=user_id,
                    telegram_id=credentials.telegram_id,
                    event_type="login_attempt",
                    event_status="failure",
                    event_message="Account locked",
                    ip_address=ip_address
                )
                return {
                    "success": False,
                    "error": "account_locked",
                    "locked_until": credentials.locked_until.isoformat()
                }

            # Check if password is set
            if not credentials.password_hash:
                return {"success": False, "error": "password_not_set"}

            # Verify password
            password_valid = bcrypt.checkpw(
                password.encode('utf-8'),
                credentials.password_hash.encode('utf-8')
            )

            if password_valid:
                # Reset failed attempts on successful login
                credentials.failed_attempts = 0
                credentials.locked_until = None
                credentials.last_login_at = datetime.utcnow()

                await self.db.commit()

                await self._log_auth_event(
                    user_id=user_id,
                    telegram_id=credentials.telegram_id,
                    event_type="password_login",
                    event_status="success",
                    ip_address=ip_address
                )

                return {
                    "success": True,
                    "mfa_required": credentials.mfa_enabled,
                    "force_password_change": credentials.force_password_change
                }
            else:
                # Handle failed attempt
                credentials.failed_attempts += 1

                # Lock account if too many failed attempts
                if credentials.failed_attempts >= settings.max_login_attempts:
                    credentials.locked_until = datetime.utcnow() + timedelta(
                        minutes=settings.lockout_duration_minutes
                    )

                await self.db.commit()

                await self._log_auth_event(
                    user_id=user_id,
                    telegram_id=credentials.telegram_id,
                    event_type="login_attempt",
                    event_status="failure",
                    event_message=f"Invalid password (attempt {credentials.failed_attempts})",
                    ip_address=ip_address
                )

                return {
                    "success": False,
                    "error": "invalid_password",
                    "attempts_remaining": max(0, settings.max_login_attempts - credentials.failed_attempts)
                }

        except Exception as e:
            logger.error(f"Error verifying password for user {user_id}: {e}")
            return {"success": False, "error": "verification_failed"}

    async def enable_mfa(self, user_id: int) -> Dict[str, Any]:
        """Enable multi-factor authentication for user"""
        try:
            credentials = await self.get_credentials_by_user_id(user_id)
            if not credentials:
                return {"success": False, "error": "credentials_not_found"}

            # Generate TOTP secret
            secret = pyotp.random_base32()

            # Generate backup codes
            backup_codes = [secrets.token_hex(8) for _ in range(10)]
            hashed_backup_codes = [
                bcrypt.hashpw(code.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                for code in backup_codes
            ]

            credentials.mfa_secret = secret  # In production, encrypt this
            credentials.backup_codes = hashed_backup_codes
            credentials.mfa_enabled = True

            await self.db.commit()

            logger.info(f"MFA enabled for user {user_id}")

            return {
                "success": True,
                "secret": secret,
                "backup_codes": backup_codes,  # Show only once
                "qr_code_url": pyotp.totp.TOTP(secret).provisioning_uri(
                    name=f"user_{user_id}",
                    issuer_name="UK Management Bot"
                )
            }

        except Exception as e:
            logger.error(f"Error enabling MFA for user {user_id}: {e}")
            await self.db.rollback()
            return {"success": False, "error": "mfa_setup_failed"}

    async def verify_mfa_token(self, user_id: int, token: str) -> bool:
        """Verify MFA token (TOTP or backup code)"""
        try:
            credentials = await self.get_credentials_by_user_id(user_id)
            if not credentials or not credentials.mfa_enabled:
                return False

            # Try TOTP first
            if credentials.mfa_secret:
                totp = pyotp.TOTP(credentials.mfa_secret)
                if totp.verify(token):
                    return True

            # Try backup codes
            if credentials.backup_codes and len(token) == 16:  # backup code length
                for i, hashed_code in enumerate(credentials.backup_codes):
                    if bcrypt.checkpw(token.encode('utf-8'), hashed_code.encode('utf-8')):
                        # Remove used backup code
                        credentials.backup_codes.pop(i)
                        await self.db.commit()
                        return True

            return False

        except Exception as e:
            logger.error(f"Error verifying MFA token for user {user_id}: {e}")
            return False

    async def _set_password(self, credentials: UserCredential, password: str):
        """Internal method to hash and set password"""
        # Validate password strength
        if len(password) < settings.password_min_length:
            raise ValueError(f"Password must be at least {settings.password_min_length} characters")

        # Generate salt and hash password
        salt = bcrypt.gensalt(rounds=settings.password_hash_rounds)
        password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)

        credentials.password_hash = password_hash.decode('utf-8')
        credentials.password_salt = salt.decode('utf-8')
        credentials.password_set_at = datetime.utcnow()

    async def _log_auth_event(
        self,
        event_type: str,
        event_status: str,
        user_id: int = None,
        telegram_id: str = None,
        event_message: str = None,
        ip_address: str = None,
        session_id: str = None,
        metadata: Dict[str, Any] = None
    ):
        """Log authentication events for audit trail"""
        try:
            auth_log = AuthLog(
                user_id=user_id,
                telegram_id=telegram_id,
                event_type=event_type,
                event_status=event_status,
                event_message=event_message,
                ip_address=ip_address,
                session_id=session_id,
                auth_metadata=metadata,
                created_at=datetime.utcnow()
            )

            self.db.add(auth_log)
            await self.db.flush()

        except Exception as e:
            logger.error(f"Error logging auth event: {e}")

    async def cleanup_expired_locks(self):
        """Cleanup expired account locks (background task)"""
        try:
            await self.db.execute(
                update(UserCredential)
                .where(UserCredential.locked_until <= datetime.utcnow())
                .values(
                    locked_until=None,
                    failed_attempts=0
                )
            )
            await self.db.commit()

            logger.debug("Cleaned up expired account locks")

        except Exception as e:
            logger.error(f"Error cleaning up expired locks: {e}")
            await self.db.rollback()