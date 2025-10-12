# Authentication Middleware for Shift Service
# UK Management Bot - Shift Service

import logging
from typing import Optional
import httpx
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer()


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware for service-to-service communication
    Validates JWT tokens with Auth Service
    """

    def __init__(self, app):
        super().__init__(app)
        self.auth_service_url = settings.auth_service_url

    async def dispatch(self, request: Request, call_next):
        # Skip authentication for health endpoints
        if request.url.path in ["/health", "/ready", "/info", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        # Skip authentication in testing environment
        if settings.environment == "testing":
            request.state.user = {
                "user_id": "00000000-0000-0000-0000-000000000001",
                "username": "test_user",
                "role": "manager",
                "permissions": ["shift:*"]
            }
            return await call_next(request)

        # Skip authentication for internal service endpoints with API key
        if request.url.path.startswith("/api/v1/internal"):
            api_key = request.headers.get("X-Service-API-Key")
            if api_key == settings.service_api_key:
                # Add service context
                request.state.user = {
                    "user_id": "system",
                    "service": "shift-service",
                    "permissions": ["internal:*"]
                }
                return await call_next(request)
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid service API key"
                )

        # Extract bearer token
        authorization = request.headers.get("Authorization")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid authorization header"
            )

        token = authorization.split(" ")[1]

        # Validate token with Auth Service
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.auth_service_url}/api/v1/auth/validate",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5.0
                )

                if response.status_code == 200:
                    user_data = response.json()
                    request.state.user = user_data
                    return await call_next(request)
                else:
                    logger.warning(f"Token validation failed: {response.status_code}")
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid token"
                    )

        except HTTPException:
            # Re-raise HTTP exceptions as-is (don't catch our own exceptions)
            raise
        except httpx.TimeoutException:
            logger.error("Auth service timeout")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable"
            )
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication error"
            )


async def get_current_user(request: Request) -> dict:
    """
    Dependency to get current authenticated user
    """
    if not hasattr(request.state, "user"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return request.state.user


async def require_permission(permission: str):
    """
    Dependency factory for permission checking
    """
    async def check_permission(current_user: dict = get_current_user):
        user_permissions = current_user.get("permissions", [])

        # Check for wildcard permissions
        if "admin:*" in user_permissions or "shift:*" in user_permissions:
            return current_user

        # Check for specific permission
        if permission in user_permissions:
            return current_user

        # Check for internal service permissions
        if permission.startswith("internal:") and "internal:*" in user_permissions:
            return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required: {permission}"
        )

    return check_permission


async def get_service_token() -> str:
    """
    Get service token for service-to-service communication
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.auth_service_url}/api/v1/internal/generate-service-token",
                headers={"X-Service-API-Key": settings.service_api_key},
                json={
                    "service_name": "shift-service",
                    "permissions": ["user:read", "request:read", "notification:send"]
                },
                timeout=5.0
            )

            if response.status_code == 200:
                return response.json()["token"]
            else:
                logger.error(f"Failed to get service token: {response.status_code}")
                raise Exception("Failed to get service token")

    except Exception as e:
        logger.error(f"Service token error: {e}")
        raise


class ServiceAuthHeaders:
    """Helper class for service authentication headers"""

    @staticmethod
    async def get_headers() -> dict:
        """Get headers for service-to-service requests"""
        token = await get_service_token()
        return {
            "Authorization": f"Bearer {token}",
            "X-Service-Name": "shift-service",
            "Content-Type": "application/json"
        }