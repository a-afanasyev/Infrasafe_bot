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

    async def generate_service_token(self) -> str:
        """
        Generate service token from Auth Service

        Returns:
            JWT service token for inter-service communication
        """
        try:
            # Check if cached token is still valid
            if (self._service_token_cache and
                self._token_expires_at and
                datetime.utcnow() < self._token_expires_at - timedelta(minutes=5)):
                return self._service_token_cache

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.auth_service_url}/api/v1/internal/generate-service-token",
                    json={
                        "service_name": self.service_name,
                        "permissions": [
                            "users:read",
                            "notifications:send",
                            "media:read"
                        ]
                    },
                    headers={
                        "X-Service-API-Key": self.service_api_key,
                        "Content-Type": "application/json"
                    }
                )

                if response.status_code != 200:
                    raise AuthenticationError(f"Failed to generate service token: {response.status_code}")

                data = response.json()
                token = data.get("token")
                expires_in = data.get("expires_in", 1800)  # 30 minutes default

                # Cache token
                self._service_token_cache = token
                self._token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

                logger.info("Generated new service token")
                return token

        except httpx.RequestError as e:
            logger.error(f"Service token generation request failed: {e}")
            raise AuthenticationError("Auth service unavailable")
        except Exception as e:
            logger.error(f"Service token generation failed: {e}")
            raise AuthenticationError(f"Token generation error: {str(e)}")

    async def validate_service_token(self, token: str) -> Dict[str, Any]:
        """
        Validate service token with Auth Service

        Args:
            token: JWT token to validate

        Returns:
            Token payload if valid

        Raises:
            AuthenticationError: If token is invalid
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self.auth_service_url}/api/v1/internal/validate-service-token",
                    json={"token": token},
                    headers={
                        "X-Service-API-Key": self.service_api_key,
                        "Content-Type": "application/json"
                    }
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    raise AuthenticationError("Invalid service token")
                else:
                    raise AuthenticationError(f"Token validation failed: {response.status_code}")

        except httpx.RequestError as e:
            logger.error(f"Token validation request failed: {e}")
            # Fallback to local validation in development
            if settings.is_development:
                return await self._validate_token_locally(token)
            raise AuthenticationError("Auth service unavailable")
        except AuthenticationError:
            raise
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            raise AuthenticationError(f"Validation error: {str(e)}")

    async def _validate_token_locally(self, token: str) -> Dict[str, Any]:
        """
        Local token validation (development fallback)

        Args:
            token: JWT token to validate

        Returns:
            Token payload if valid
        """
        try:
            # Decode without verification in development
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
                options={"verify_exp": True}
            )

            return {
                "valid": True,
                "payload": payload,
                "service_name": payload.get("service_name"),
                "permissions": payload.get("permissions", [])
            }

        except JWTError as e:
            logger.warning(f"Local token validation failed: {e}")
            raise AuthenticationError("Invalid token format")

    async def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user information from User Service

        Args:
            user_id: User ID to lookup

        Returns:
            User information or None if not found
        """
        try:
            service_token = await self.generate_service_token()

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.user_service_url}/api/v1/users/{user_id}",
                    headers={
                        "Authorization": f"Bearer {service_token}",
                        "Content-Type": "application/json"
                    }
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    return None
                else:
                    logger.warning(f"User lookup failed for {user_id}: {response.status_code}")
                    return None

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

    try:
        # Validate token
        token_data = await auth_manager.validate_service_token(credentials.credentials)

        if not token_data.get("valid"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Extract service information from Auth Service response
        # Format: {valid: bool, service_name: str, permissions: list, expires_at: str}
        service_name = token_data.get("service_name")
        if service_name:
            return {
                "type": "service",
                "service_name": service_name,
                "permissions": token_data.get("permissions", [])
            }

        # If no service_name, this might be a user token (not currently supported)
        # Note: User token support would need to be implemented based on Auth Service format

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service error"
        )


async def require_service_auth(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Dependency to require service authentication

    Returns:
        Service information

    Raises:
        HTTPException: If not a service token
    """
    if current_user.get("type") != "service":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Service authentication required"
        )

    return current_user


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
    Dependency factory to require specific permissions

    Args:
        required_permissions: List of required permissions

    Returns:
        Dependency function
    """
    async def _require_permissions(
        current_user: Dict[str, Any] = Depends(get_current_user)
    ) -> Dict[str, Any]:

        if current_user.get("type") == "service":
            # Check service permissions
            service_permissions = current_user.get("permissions", [])
            if not all(perm in service_permissions for perm in required_permissions):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient service permissions"
                )

        elif current_user.get("type") == "user":
            # Check user permissions
            user_id = current_user.get("user_id")
            if not await auth_manager.verify_user_permissions(user_id, required_permissions):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient user permissions"
                )

        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication type"
            )

        return current_user

    return _require_permissions


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """
    Dependency to get optional authenticated user (no error if not authenticated)

    Returns:
        User information or None
    """
    if not credentials:
        return None

    try:
        return await get_current_user(credentials)
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
            service_token = await self.auth_manager.generate_service_token()
            headers["Authorization"] = f"Bearer {service_token}"
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