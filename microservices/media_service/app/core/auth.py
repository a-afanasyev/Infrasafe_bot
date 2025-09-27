"""
Authentication and authorization utilities for Media Service
"""

import logging
from typing import Optional, Dict, Any
from fastapi import HTTPException, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """
    Get current user from JWT token
    TODO: Integrate with Auth Service for proper token validation
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    # For now, return a mock user
    # In production, this should validate the JWT with Auth Service
    return {
        "user_id": 1,
        "username": "system",
        "roles": ["admin"]
    }


async def require_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> Dict[str, Any]:
    """
    Require API key for service-to-service authentication
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")

    # Check if API key is in allowed list
    if settings.api_keys and x_api_key not in settings.api_keys:
        raise HTTPException(status_code=403, detail="Invalid API key")

    # For development, allow any non-empty API key if no keys configured
    if not settings.api_keys and x_api_key:
        logger.warning("Using development mode - any API key accepted")

    return {
        "api_key": x_api_key,
        "service": "external",
        "permissions": ["upload", "read"]
    }


async def require_admin(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Require admin role
    """
    if "admin" not in current_user.get("roles", []):
        raise HTTPException(status_code=403, detail="Admin access required")

    return current_user


def check_upload_permissions(user: Dict[str, Any], request_number: str) -> bool:
    """
    Check if user has permission to upload media for specific request
    TODO: Integrate with Auth Service for proper permission checking
    """
    # For now, allow all authenticated users
    return True


def check_access_permissions(user: Dict[str, Any], media_file_id: int) -> bool:
    """
    Check if user has permission to access specific media file
    TODO: Integrate with Auth Service for proper permission checking
    """
    # For now, allow all authenticated users
    return True