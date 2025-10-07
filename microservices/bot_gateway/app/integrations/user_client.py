"""
User Service Client
UK Management Bot - Bot Gateway Service

Client for User Service communication.
"""

import logging
from typing import Optional, Dict, Any, List
from uuid import UUID

from app.core.config import settings
from .base_client import BaseServiceClient

logger = logging.getLogger(__name__)


class UserServiceClient(BaseServiceClient):
    """
    User Service Client

    Handles user management operations:
    - Get user profile
    - Update user information
    - User role management
    - User search and listing
    """

    def __init__(self):
        super().__init__(
            base_url=settings.USER_SERVICE_URL,
            service_name="UserService"
        )

    async def get_user(self, user_id: UUID, token: str) -> Dict[str, Any]:
        """
        Get user by ID.

        Args:
            user_id: User UUID
            token: JWT access token

        Returns:
            User information
        """
        response = await self.get(
            endpoint=f"/api/v1/users/{user_id}",
            token=token
        )
        return response.json()

    async def get_user_by_telegram_id(
        self,
        telegram_id: int,
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get user by Telegram ID.

        Args:
            telegram_id: Telegram user ID
            token: JWT access token (optional for internal calls)

        Returns:
            User information
        """
        response = await self.get(
            endpoint=f"/api/v1/users/telegram/{telegram_id}",
            token=token
        )
        return response.json()

    async def update_user(
        self,
        user_id: UUID,
        data: Dict[str, Any],
        token: str
    ) -> Dict[str, Any]:
        """
        Update user information.

        Args:
            user_id: User UUID
            data: Update data
            token: JWT access token

        Returns:
            Updated user information
        """
        response = await self.put(
            endpoint=f"/api/v1/users/{user_id}",
            data=data,
            token=token
        )
        return response.json()

    async def get_user_role(self, user_id: UUID, token: str) -> str:
        """
        Get user's primary role.

        Args:
            user_id: User UUID
            token: JWT access token

        Returns:
            User role: applicant, executor, manager, admin
        """
        response = await self.get(
            endpoint=f"/api/v1/users/{user_id}/role",
            token=token
        )
        result = response.json()
        return result.get("role", "applicant")

    async def search_users(
        self,
        query: str,
        role: Optional[str] = None,
        limit: int = 10,
        token: str = None
    ) -> List[Dict[str, Any]]:
        """
        Search users by name or phone.

        Args:
            query: Search query
            role: Filter by role (optional)
            limit: Maximum results
            token: JWT access token

        Returns:
            List of matching users
        """
        params = {
            "q": query,
            "limit": limit
        }
        if role:
            params["role"] = role

        response = await self.get(
            endpoint="/api/v1/users/search",
            params=params,
            token=token
        )
        return response.json()

    async def get_executors(
        self,
        specialization: Optional[str] = None,
        available_only: bool = False,
        token: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get list of executors.

        Args:
            specialization: Filter by specialization
            available_only: Only available executors
            token: JWT access token

        Returns:
            List of executors
        """
        params = {}
        if specialization:
            params["specialization"] = specialization
        if available_only:
            params["available_only"] = "true"

        response = await self.get(
            endpoint="/api/v1/users/executors",
            params=params,
            token=token
        )
        return response.json()

    async def set_user_language(
        self,
        user_id: UUID,
        language: str,
        token: str
    ) -> Dict[str, Any]:
        """
        Set user's preferred language.

        Args:
            user_id: User UUID
            language: Language code (ru, uz)
            token: JWT access token

        Returns:
            Updated user information
        """
        response = await self.patch(
            endpoint=f"/api/v1/users/{user_id}/language",
            data={"language": language},
            token=token
        )
        return response.json()


# Global User Service client instance
user_client = UserServiceClient()
