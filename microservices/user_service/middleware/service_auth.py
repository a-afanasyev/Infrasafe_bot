# Service Authentication Middleware for User Service
# UK Management Bot - User Service

import logging
import httpx
from typing import Dict, Any, Optional
from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

class ServiceAuthMiddleware:
    """Middleware for validating service-to-service authentication"""

    def __init__(self):
        self.auth_service_url = getattr(settings, 'auth_service_url', 'http://auth-service:8000')

    async def validate_service_token(self, token: str, expected_service: str = None) -> Optional[Dict[str, Any]]:
        """
        Validate service token with Auth Service

        Args:
            token: Service token to validate
            expected_service: Expected service name (optional)

        Returns:
            Service information if valid, None if invalid
        """
        try:
            # Call Auth Service to validate the token
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self.auth_service_url}/api/v1/internal/validate-service-token",
                    json={
                        "token": token,
                        "service_name": expected_service
                    },
                    headers={"Content-Type": "application/json"}
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get("valid"):
                        logger.debug(f"Service token validated for {result.get('service_name')}")
                        return result
                    else:
                        logger.warning("Service token validation failed")
                        return None

                else:
                    logger.error(f"Auth Service validation error {response.status_code}: {response.text}")
                    return None

        except httpx.RequestError as e:
            logger.error(f"Failed to connect to Auth Service for token validation: {e}")
            return None
        except Exception as e:
            logger.error(f"Error validating service token: {e}")
            return None

    async def validate_api_key(self, api_key: str) -> Optional[str]:
        """
        Simple API key validation for development
        Format: service-name.hash
        """
        try:
            if "." not in api_key:
                return None

            service_name = api_key.split(".")[0]

            # Check if service is in allowed list
            allowed_services = getattr(settings, 'allowed_services', [
                "auth-service",
                "request-service",
                "shift-service",
                "notification-service",
                "analytics-service",
                "ai-service"
            ])

            if service_name in allowed_services:
                return service_name

            return None

        except Exception as e:
            logger.error(f"Error validating API key: {e}")
            return None

# Global middleware instance
service_auth = ServiceAuthMiddleware()

async def require_service_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    request: Request = None
) -> Dict[str, Any]:
    """
    Dependency that requires service authentication
    Can be used to protect endpoints that should only be called by other services
    """
    # Check for Authorization header
    if credentials:
        token = credentials.credentials

        # Try service token validation first
        service_info = await service_auth.validate_service_token(token)
        if service_info:
            return service_info

    # Check for X-API-Key header as fallback
    api_key = request.headers.get("X-API-Key") if request else None
    if api_key:
        service_name = await service_auth.validate_api_key(api_key)
        if service_name:
            return {
                "service_name": service_name,
                "token_type": "api_key",
                "valid": True
            }

    # If we get here, authentication failed
    raise HTTPException(
        status_code=401,
        detail="Service authentication required"
    )

def require_specific_service(allowed_service: str):
    """
    Dependency factory that requires authentication from a specific service

    Usage:
        @app.get("/endpoint")
        async def endpoint(service_info = Depends(require_specific_service("auth-service"))):
            pass
    """
    async def _require_specific_service(
        service_info: Dict[str, Any] = Depends(require_service_auth)
    ) -> Dict[str, Any]:
        if service_info.get("service_name") != allowed_service:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Expected service: {allowed_service}"
            )
        return service_info

    return _require_specific_service