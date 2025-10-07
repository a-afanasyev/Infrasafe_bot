"""
Auth Service Client
UK Management Bot - Bot Gateway Service

Client for Auth Service communication.
"""

import logging
from typing import Optional, Dict, Any

from app.core.config import settings
from .base_client import BaseServiceClient

logger = logging.getLogger(__name__)


class AuthServiceClient(BaseServiceClient):
    """
    Auth Service Client

    Handles authentication and authorization operations:
    - User login/logout
    - Token validation
    - Permission checks
    - Session management
    """

    def __init__(self):
        super().__init__(
            base_url=settings.AUTH_SERVICE_URL,
            service_name="AuthService"
        )

    async def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate JWT access token.

        Args:
            token: JWT access token

        Returns:
            Token payload with user information

        Raises:
            httpx.HTTPStatusError: If token is invalid
        """
        response = await self.post(
            endpoint="/api/v1/auth/validate-token",
            data={"token": token}
        )
        return response.json()

    async def login_telegram(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Login user via Telegram authentication.

        Args:
            telegram_id: Telegram user ID
            username: Telegram username
            first_name: Telegram first name
            last_name: Telegram last name

        Returns:
            {
                "access_token": "...",
                "token_type": "bearer",
                "user": {...}
            }
        """
        response = await self.post(
            endpoint="/api/v1/auth/telegram/login",
            data={
                "telegram_id": telegram_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name
            }
        )
        return response.json()

    async def check_permission(
        self,
        token: str,
        resource: str,
        action: str
    ) -> bool:
        """
        Check if user has permission for resource action.

        Args:
            token: JWT access token
            resource: Resource name (e.g., "request", "shift")
            action: Action name (e.g., "create", "update", "delete")

        Returns:
            True if user has permission, False otherwise
        """
        try:
            response = await self.post(
                endpoint="/api/v1/auth/check-permission",
                data={
                    "resource": resource,
                    "action": action
                },
                token=token
            )
            result = response.json()
            return result.get("has_permission", False)
        except Exception as e:
            logger.error(f"Permission check failed: {e}")
            return False

    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh access token using refresh token.

        Args:
            refresh_token: JWT refresh token

        Returns:
            New access token and refresh token
        """
        response = await self.post(
            endpoint="/api/v1/auth/refresh",
            data={"refresh_token": refresh_token}
        )
        return response.json()

    async def logout(self, token: str) -> Dict[str, Any]:
        """
        Logout user and invalidate session.

        Args:
            token: JWT access token

        Returns:
            Logout confirmation
        """
        response = await self.post(
            endpoint="/api/v1/auth/logout",
            data={},
            token=token
        )
        return response.json()

    async def get_current_user(self, token: str) -> Dict[str, Any]:
        """
        Get current user information from token.

        Args:
            token: JWT access token

        Returns:
            User information
        """
        response = await self.get(
            endpoint="/api/v1/auth/me",
            token=token
        )
        return response.json()


# Global Auth Service client instance
auth_client = AuthServiceClient()
