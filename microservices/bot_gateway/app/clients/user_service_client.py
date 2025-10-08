"""
User Service Client
UK Management Bot - Bot Gateway Service

HTTP client for User Service API endpoints.
"""

import logging
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime

import httpx
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)


# Request/Response Models
class UserCreateRequest(BaseModel):
    """Request model for user creation"""
    telegram_id: int = Field(..., description="Telegram user ID")
    username: Optional[str] = Field(None, description="Telegram username")
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    language_code: str = Field(default="ru", description="Language code")
    phone_number: Optional[str] = Field(None, description="Phone number")


class UserResponse(BaseModel):
    """Response model for user data"""
    id: str = Field(..., description="User ID (can be int or UUID)")
    telegram_id: int = Field(..., description="Telegram user ID")
    username: Optional[str] = Field(None, description="Telegram username")
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    phone_number: Optional[str] = Field(None, description="Phone number")
    language_code: str = Field(..., description="Language code")
    role: Optional[str] = Field(None, description="User role")
    status: str = Field(..., description="User status")
    is_active: bool = Field(..., description="Is user active")
    created_at: datetime = Field(..., description="Creation timestamp")


class UserServiceClient:
    """HTTP client for User Service."""

    def __init__(self):
        """Initialize User Service client."""
        self.base_url = settings.USER_SERVICE_URL
        self.timeout = settings.HTTP_TIMEOUT_SECONDS
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "Content-Type": "application/json",
                "X-Service-Name": "bot-gateway",
                "X-API-Key": "bot-gateway.dev-key-12345"
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()

    async def get_user_by_telegram_id(
        self,
        telegram_id: int
    ) -> Optional[UserResponse]:
        """
        Get user by Telegram ID.

        Args:
            telegram_id: Telegram user ID

        Returns:
            UserResponse if found, None otherwise

        Raises:
            httpx.HTTPError: On HTTP request errors
        """
        try:
            response = await self.client.get(
                f"/api/v1/internal/users/telegram/{telegram_id}"
            )

            if response.status_code == 404:
                logger.debug(f"User not found for telegram_id={telegram_id}")
                return None

            response.raise_for_status()
            data = response.json()

            logger.info(f"Retrieved user {data.get('id')} for telegram_id={telegram_id}")
            return UserResponse(**data)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting user by telegram_id: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting user by telegram_id: {e}")
            raise

    async def create_user(
        self,
        user_data: UserCreateRequest
    ) -> UserResponse:
        """
        Create a new user.

        Args:
            user_data: User creation data

        Returns:
            Created UserResponse

        Raises:
            httpx.HTTPError: On HTTP request errors
        """
        try:
            response = await self.client.post(
                "/api/v1/internal/users",
                json=user_data.model_dump(exclude_none=True)
            )
            response.raise_for_status()
            data = response.json()

            logger.info(
                f"Created user {data.get('id')} for telegram_id={user_data.telegram_id}"
            )
            return UserResponse(**data)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error creating user: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating user: {e}")
            raise

    async def get_or_create_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        language_code: str = "ru"
    ) -> UserResponse:
        """
        Get existing user or create if not exists.

        Args:
            telegram_id: Telegram user ID
            username: Telegram username
            first_name: First name
            last_name: Last name
            language_code: Language code

        Returns:
            UserResponse (existing or newly created)

        Raises:
            httpx.HTTPError: On HTTP request errors
        """
        # Try to get existing user
        user = await self.get_user_by_telegram_id(telegram_id)

        if user:
            logger.debug(f"Found existing user {user.id} for telegram_id={telegram_id}")
            return user

        # Create new user
        logger.info(f"Creating new user for telegram_id={telegram_id}")
        user_data = UserCreateRequest(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code
        )

        return await self.create_user(user_data)


# Singleton instance
_user_service_client: Optional[UserServiceClient] = None


def get_user_service_client() -> UserServiceClient:
    """
    Get singleton User Service client instance.

    Returns:
        UserServiceClient instance
    """
    global _user_service_client
    if _user_service_client is None:
        _user_service_client = UserServiceClient()
    return _user_service_client
