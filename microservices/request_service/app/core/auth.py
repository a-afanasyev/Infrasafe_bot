"""
Request Service - Authentication and Authorization
UK Management Bot - Request Management System

Service-to-service authentication and user authorization middleware.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from fastapi import HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import httpx
from functools import wraps

from app.core.config import settings

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer(auto_error=False)


class AuthenticationError(Exception):
    """Custom authentication error"""
    pass


class AuthorizationError(Exception):
    """Custom authorization error"""
    pass


class ServiceAuthManager:
    """
    Service-to-service authentication manager

    Handles JWT token validation and service communication.
    """

    def __init__(self):
        self.auth_service_url = settings.AUTH_SERVICE_URL
        self.user_service_url = settings.USER_SERVICE_URL
        self.service_name = settings.SERVICE_NAME
        self.service_api_key = settings.SERVICE_API_KEY
        self._service_token_cache: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    def get_service_auth_headers(self) -> Dict[str, str]:
        """
        Get service authentication headers for inter-service calls
        Uses static API key authentication instead of JWT tokens

        Returns:
            Headers dict with service authentication
        """
        return {
            "X-Service-Name": self.service_name,
            "X-Service-API-Key": self.service_api_key,
            "Content-Type": "application/json"
        }

    async def call_service(
        self,
        service_url: str,
        endpoint: str,
        method: str = "GET",
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make authenticated call to another service using static API keys

        Args:
            service_url: Target service base URL
            endpoint: API endpoint path
            method: HTTP method
            data: Request payload

        Returns:
            Response data
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                request_kwargs = {
                    "method": method,
                    "url": f"{service_url}{endpoint}",
                    "headers": self.get_service_auth_headers()
                }

                if data and method.upper() in ["POST", "PUT", "PATCH"]:
                    request_kwargs["json"] = data
                elif data and method.upper() == "GET":
                    request_kwargs["params"] = data

                response = await client.request(**request_kwargs)

                if response.status_code >= 400:
                    logger.error(f"Service call failed: {response.status_code} - {response.text}")
                    raise AuthenticationError(f"Service call failed: {response.status_code}")

                return response.json()

        except httpx.RequestError as e:
            logger.error(f"Service call request failed: {e}")
            raise AuthenticationError(f"Service unavailable: {str(e)}")
        except Exception as e:
            logger.error(f"Service call failed: {e}")
            raise AuthenticationError(f"Service call error: {str(e)}")

    # SECURITY: JWT self-minting and local validation removed
    # Services now use static API key authentication for security

    async def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user information from User Service

        Args:
            user_id: User ID to lookup

        Returns:
            User information or None if not found
        """
        try:
            return await self.call_service(
                service_url=self.user_service_url,
                endpoint=f"/api/v1/users/{user_id}",
                method="GET"
            )


        except Exception as e:
            logger.error(f"User lookup error for {user_id}: {e}")
            return None

    async def verify_user_permissions(
        self,
        user_id: str,
        required_permissions: List[str]
    ) -> bool:
        """
        Verify user has required permissions

        Args:
            user_id: User ID to check
            required_permissions: List of required permissions

        Returns:
            True if user has all required permissions
        """
        try:
            user_info = await self.get_user_info(user_id)
            if not user_info:
                return False

            user_permissions = user_info.get("permissions", [])
            return all(perm in user_permissions for perm in required_permissions)

        except Exception as e:
            logger.error(f"Permission verification error for {user_id}: {e}")
            return False


# Global auth manager instance
auth_manager = ServiceAuthManager()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """
    Dependency to get current authenticated user

    IMPORTANT: Request Service should NOT validate user tokens directly.
    User authentication should be handled by API Gateway or Auth Service.
    This method is only for service-to-service calls within internal network.

    Returns:
        User information from token

    Raises:
        HTTPException: If authentication fails
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Request Service should not validate external user tokens
    # This creates a circular dependency with Auth Service
    # External users should authenticate through API Gateway or Auth Service directly

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Request Service does not validate user tokens. Use API Gateway or Auth Service for authentication."
    )


async def require_service_auth(
    request: Request
) -> Dict[str, Any]:
    """
    Dependency to require service authentication via X-Service-API-Key headers

    Args:
        request: FastAPI request object

    Returns:
        Service information

    Raises:
        HTTPException: If not authenticated as service
    """
    service_name = request.headers.get("X-Service-Name")
    service_api_key = request.headers.get("X-Service-API-Key")

    if not service_name or not service_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Service authentication required: X-Service-Name and X-Service-API-Key headers missing"
        )

    # Validate against known service credentials
    expected_keys = {
        "request-service": "request-service-api-key-change-in-production",
        "user-service": "user-service-api-key-change-in-production",
        "notification-service": "notification-service-api-key-change-in-production",
        "media-service": "media-service-api-key-change-in-production",
        "ai-service": "ai-service-api-key-change-in-production",
        "auth-service": "auth-service-api-key-change-in-production"
    }

    expected_key = expected_keys.get(service_name)
    if not expected_key or service_api_key != expected_key:
        logger.warning(f"Invalid service credentials: {service_name}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid service credentials"
        )

    return {
        "type": "service",
        "service_name": service_name,
        "authenticated": True
    }


async def require_specific_service(
    allowed_services: List[str]
):
    """
    Dependency factory to require specific service authentication

    Args:
        allowed_services: List of allowed service names

    Returns:
        Dependency function
    """
    async def _require_specific_service(
        service_info: Dict[str, Any] = Depends(require_service_auth)
    ) -> Dict[str, Any]:
        service_name = service_info.get("service_name")

        if service_name not in allowed_services:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Service {service_name} not authorized for this endpoint"
            )

        return service_info

    return _require_specific_service


def require_permissions(required_permissions: List[str]):
    """
    Dependency factory to require specific permissions for service calls only

    Args:
        required_permissions: List of required permissions

    Returns:
        Dependency function
    """
    async def _require_permissions(
        request: Request
    ) -> Dict[str, Any]:
        # Only handle service authentication
        # User permission validation should be done at API Gateway level
        service_info = await require_service_auth(request)

        # For now, all authenticated services have all permissions
        # In production, this should validate against service-specific permissions
        logger.info(f"Service {service_info['service_name']} authorized with permissions: {required_permissions}")

        return service_info

    return _require_permissions


async def get_optional_user(
    request: Request
) -> Optional[Dict[str, Any]]:
    """
    Dependency to get optional authenticated user (no error if not authenticated)

    Returns:
        Service information or None
    """
    try:
        return await require_service_auth(request)
    except HTTPException:
        return None


# Middleware for automatic service authentication
class ServiceAuthMiddleware:
    """
    Middleware to add service authentication to outgoing requests
    """

    def __init__(self):
        self.auth_manager = auth_manager

    async def add_service_auth(self, headers: Dict[str, str]) -> Dict[str, str]:
        """
        Add service authentication to request headers

        Args:
            headers: Existing headers dictionary

        Returns:
            Headers with authentication added
        """
        try:
            # Use static service credentials instead of JWT tokens
            auth_headers = self.auth_manager.get_service_auth_headers()
            headers.update(auth_headers)
            return headers
        except Exception as e:
            logger.error(f"Failed to add service auth: {e}")
            return headers


# Global middleware instance
service_auth_middleware = ServiceAuthMiddleware()


async def verify_internal_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Simple internal API token verification for bot integration

    Args:
        credentials: HTTP Bearer credentials

    Returns:
        str: The token if valid

    Raises:
        HTTPException: If token is invalid or missing
    """
    if not credentials:
        logger.warning("Missing authorization credentials for internal API")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Verify the token matches our internal API token
    if token != settings.INTERNAL_API_TOKEN:
        logger.warning(f"Invalid internal API token attempted: {token[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.debug("Internal API token verified successfully")
    return token