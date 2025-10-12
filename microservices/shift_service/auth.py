# Authentication utilities for Shift Service
# UK Management Bot - Shift Service

from typing import Dict, Any, List
from fastapi import HTTPException, Depends, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()


async def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Get current user from request state (set by AuthMiddleware)

    Args:
        request: FastAPI Request object

    Returns:
        User data dict with user_id, role, permissions

    Raises:
        HTTPException: If user not authenticated
    """
    if not hasattr(request.state, 'user'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    return request.state.user


def require_role(user: Dict[str, Any], allowed_roles: List[str]) -> None:
    """
    Check if user has required role

    Args:
        user: User data dict from get_current_user
        allowed_roles: List of allowed roles

    Raises:
        HTTPException: If user doesn't have required role
    """
    user_role = user.get("role")

    if user_role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required roles: {allowed_roles}"
        )


def require_permission(user: Dict[str, Any], required_permission: str) -> None:
    """
    Check if user has required permission

    Args:
        user: User data dict from get_current_user
        required_permission: Required permission string

    Raises:
        HTTPException: If user doesn't have permission
    """
    permissions = user.get("permissions", [])

    # Check exact match or wildcard
    if required_permission not in permissions:
        # Check wildcards (e.g., "shift:*" covers "shift:read")
        prefix = required_permission.split(":")[0] + ":*"
        if prefix not in permissions and "*" not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {required_permission}"
            )
