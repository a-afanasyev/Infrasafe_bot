# Authentication Service
# UK Management Bot - Auth Service

import logging
import httpx
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.service_token import service_token_manager
from services.credential_service import CredentialService

logger = logging.getLogger(__name__)

class AuthService:
    """Service for user authentication and validation"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_service_url = settings.user_service_url
        self.credential_service = CredentialService(db)

    async def authenticate_user(self, telegram_id: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate user by telegram_id
        This method calls User Service to verify user exists and get user data
        """
        try:
            # For now, simulate user service response
            # In production, this would call the actual User Service
            user_data = await self._get_user_from_user_service(telegram_id)

            if not user_data:
                logger.warning(f"User not found: {telegram_id}")
                return None

            # Validate user is active
            if not user_data.get("is_active", True):
                logger.warning(f"User is inactive: {telegram_id}")
                return None

            return user_data

        except Exception as e:
            logger.error(f"Error authenticating user {telegram_id}: {e}")
            return None

    async def _get_user_from_user_service(self, telegram_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user data from User Service via HTTP API
        """
        try:
            # Make HTTP call to User Service
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.user_service_url}/api/v1/users/by-telegram/{telegram_id}",
                    headers={
                        "Authorization": f"Bearer {await self._get_service_token()}",
                        "Content-Type": "application/json"
                    }
                )

                if response.status_code == 200:
                    user_data = response.json()
                    logger.info(f"User found in User Service: {telegram_id}")

                    # Transform User Service response to Auth Service format
                    # Extract role keys from UserRoleMappingResponse objects
                    roles = []
                    if "roles" in user_data and user_data["roles"]:
                        roles = [role["role_key"] if isinstance(role, dict) else role for role in user_data["roles"]]

                    return {
                        "user_id": user_data["id"],
                        "telegram_id": str(user_data["telegram_id"]),
                        "username": user_data.get("username"),
                        "full_name": f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip(),
                        "roles": roles,
                        "is_active": user_data.get("is_active", False),
                        "is_verified": user_data.get("verification_status") == "approved",
                        "language_code": user_data.get("language_code", "ru"),
                        "status": user_data.get("status", "pending")
                    }

                elif response.status_code == 404:
                    logger.warning(f"User not found in User Service: {telegram_id}")
                    return None

                else:
                    logger.error(f"User Service error {response.status_code}: {response.text}")
                    # In production, fail if User Service is unavailable
                    if not settings.debug:
                        return None
                    # Only use fallback in development mode
                    return await self._get_fallback_user_data(telegram_id)

        except httpx.RequestError as e:
            logger.error(f"Failed to connect to User Service: {e}")
            # In production, fail if User Service is unavailable
            if not settings.debug:
                return None
            # Only use fallback in development mode
            return await self._get_fallback_user_data(telegram_id)

        except Exception as e:
            logger.error(f"Error fetching user from User Service: {e}")
            return None

    async def _get_service_token(self) -> str:
        """
        Get service-to-service authentication token
        Generates a JWT token for authenticating with other services
        """
        try:
            # Generate service token for auth-service to call user-service
            token = service_token_manager.generate_service_token(
                service_name="auth-service",
                permissions=["users:read", "users:write", "roles:read"]
            )
            return token

        except Exception as e:
            logger.error(f"Error generating service token: {e}")
            # Fallback to API key for development
            return service_token_manager.generate_api_key("auth-service")

    async def _get_fallback_user_data(self, telegram_id: str) -> Optional[Dict[str, Any]]:
        """
        Fallback user data when User Service is unavailable
        ⚠️  DEVELOPMENT ONLY - This method should never be called in production!
        In production, authentication must fail if User Service is unavailable.
        """
        if not settings.debug:
            logger.error("Fallback user data called in production mode - this should not happen!")
            return None

        logger.warning(f"🔧 DEVELOPMENT MODE: Using fallback user data for telegram_id: {telegram_id}")

        # Mock admin user for testing only
        if telegram_id == "123456789":
            return {
                "user_id": 1,
                "telegram_id": "123456789",
                "username": "admin",
                "full_name": "System Administrator",
                "roles": ["admin"],
                "is_active": True,
                "is_verified": True,
                "language_code": "ru",
                "status": "approved"
            }

        # No other fallback users - force proper User Service integration
        return None

    async def validate_user_permissions(self, user_id: int, telegram_id: str, permission: str) -> bool:
        """
        Validate if user has specific permission
        This method calls User Service to check user permissions
        """
        try:
            # Mock permission validation for development
            # In production, this would call User Service or Permission Service
            user_data = await self._get_user_from_user_service(telegram_id)

            if not user_data:
                return False

            user_roles = user_data.get("roles", [])

            # Admin has all permissions
            if "admin" in user_roles or "superadmin" in user_roles:
                return True

            # Basic permission mapping (will be expanded)
            role_permissions = {
                "manager": [
                    "requests:read", "requests:create", "requests:update", "requests:assign",
                    "users:read", "shifts:read", "shifts:create", "shifts:update",
                    "notifications:send", "analytics:read"
                ],
                "executor": [
                    "requests:read", "requests:update_own", "shifts:read_own",
                    "notifications:read"
                ],
                "applicant": [
                    "requests:create", "requests:read_own", "notifications:read"
                ]
            }

            # Check if any of user's roles has the required permission
            for role in user_roles:
                if role in role_permissions and permission in role_permissions[role]:
                    return True

            return False

        except Exception as e:
            logger.error(f"Error validating user permissions: {e}")
            return False

    async def get_user_roles(self, user_id: int, telegram_id: str) -> list:
        """Get user roles from User Service"""
        try:
            user_data = await self._get_user_from_user_service(telegram_id)
            if user_data:
                return user_data.get("roles", [])
            return []

        except Exception as e:
            logger.error(f"Error getting user roles: {e}")
            return []

    async def is_user_admin(self, user_id: int, telegram_id: str) -> bool:
        """Check if user has admin role"""
        try:
            roles = await self.get_user_roles(user_id, telegram_id)
            return any(role in ["admin", "superadmin"] for role in roles)

        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            return False

    async def authenticate_with_password(
        self,
        telegram_id: str,
        password: str,
        ip_address: str = None
    ) -> Dict[str, Any]:
        """
        Authenticate user with telegram_id and password
        """
        try:
            # First get user from User Service
            user_data = await self._get_user_from_user_service(telegram_id)
            if not user_data:
                logger.warning(f"User not found for password auth: {telegram_id}")
                return {"success": False, "error": "user_not_found"}

            user_id = user_data["user_id"]

            # Check if user credentials exist, create if not
            credentials = await self.credential_service.get_credentials_by_user_id(user_id)
            if not credentials:
                # Create credentials for existing user
                credentials = await self.credential_service.create_user_credentials(
                    user_id=user_id,
                    telegram_id=telegram_id
                )

            # Verify password
            auth_result = await self.credential_service.verify_password(
                user_id=user_id,
                password=password,
                ip_address=ip_address
            )

            if auth_result["success"]:
                # Include user data in successful response
                auth_result["user_data"] = user_data

            return auth_result

        except Exception as e:
            logger.error(f"Error in password authentication: {e}")
            return {"success": False, "error": "authentication_failed"}

    async def set_user_password(self, telegram_id: str, password: str, force_change: bool = False) -> bool:
        """
        Set password for user
        """
        try:
            # Get user from User Service
            user_data = await self._get_user_from_user_service(telegram_id)
            if not user_data:
                logger.warning(f"User not found for password setting: {telegram_id}")
                return False

            user_id = user_data["user_id"]

            # Ensure credentials exist
            credentials = await self.credential_service.get_credentials_by_user_id(user_id)
            if not credentials:
                credentials = await self.credential_service.create_user_credentials(
                    user_id=user_id,
                    telegram_id=telegram_id
                )

            # Set password
            return await self.credential_service.set_password(
                user_id=user_id,
                password=password,
                force_change=force_change
            )

        except Exception as e:
            logger.error(f"Error setting password for {telegram_id}: {e}")
            return False

    async def enable_mfa_for_user(self, telegram_id: str) -> Dict[str, Any]:
        """
        Enable multi-factor authentication for user
        """
        try:
            user_data = await self._get_user_from_user_service(telegram_id)
            if not user_data:
                return {"success": False, "error": "user_not_found"}

            user_id = user_data["user_id"]
            return await self.credential_service.enable_mfa(user_id)

        except Exception as e:
            logger.error(f"Error enabling MFA for {telegram_id}: {e}")
            return {"success": False, "error": "mfa_setup_failed"}

    async def verify_mfa_token(self, telegram_id: str, token: str) -> bool:
        """
        Verify MFA token for user
        """
        try:
            user_data = await self._get_user_from_user_service(telegram_id)
            if not user_data:
                return False

            user_id = user_data["user_id"]
            return await self.credential_service.verify_mfa_token(user_id, token)

        except Exception as e:
            logger.error(f"Error verifying MFA token for {telegram_id}: {e}")
            return False

    async def validate_service_token(self, token: str, expected_service: str = None) -> Optional[Dict[str, Any]]:
        """
        Validate inter-service authentication token
        This will be used for service-to-service communication
        """
        try:
            # First try JWT token validation
            payload = service_token_manager.validate_service_token(token, expected_service)
            if payload:
                return payload

            # Fallback to API key validation for development
            service_name = service_token_manager.validate_api_key(token)
            if service_name:
                return {
                    "service_name": service_name,
                    "token_type": "api_key",
                    "permissions": service_token_manager._get_default_permissions(service_name)
                }

            return None

        except Exception as e:
            logger.error(f"Error validating service token: {e}")
            return None