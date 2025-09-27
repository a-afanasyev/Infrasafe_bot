# Authentication Middleware and Dependencies
# UK Management Bot - Auth Service

import logging
from typing import Dict, Any, Optional

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from services.jwt_service import JWTService
from services.session_service import SessionService
from database import get_db

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

# JWT service instance
jwt_service = JWTService()

async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db = Depends(get_db)
) -> Optional[Dict[str, Any]]:
    """
    Get current user from JWT token (optional - doesn't raise error if no token)
    """
    if not credentials:
        return None

    try:
        # Validate token
        payload = jwt_service.validate_access_token(credentials.credentials)

        # Verify session is still active
        session_service = SessionService(db)
        session = await session_service.get_session(payload["session_id"])

        if not session or not session.is_active:
            return None

        # Update last activity
        await session_service.update_last_activity(session.session_id)

        return payload

    except Exception as e:
        logger.warning(f"Optional auth failed: {e}")
        return None

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get current user from JWT token (required - raises error if no valid token)
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # Validate token
        payload = jwt_service.validate_access_token(credentials.credentials)

        # Verify session is still active
        session_service = SessionService(db)
        session = await session_service.get_session(payload["session_id"])

        if not session or not session.is_active:
            raise HTTPException(status_code=401, detail="Session expired")

        # Update last activity
        await session_service.update_last_activity(session.session_id)

        return payload

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

def require_auth(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Dependency that requires authentication
    """
    return current_user

def require_admin(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Dependency that requires admin role
    """
    user_roles = current_user.get("roles", [])

    if not any(role in ["admin", "superadmin"] for role in user_roles):
        raise HTTPException(status_code=403, detail="Admin access required")

    return current_user

def require_role(required_role: str):
    """
    Dependency factory that requires specific role
    """
    def role_checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_roles = current_user.get("roles", [])

        if required_role not in user_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{required_role}' required"
            )

        return current_user

    return role_checker

def require_any_role(required_roles: list):
    """
    Dependency factory that requires any of the specified roles
    """
    def role_checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_roles = current_user.get("roles", [])

        if not any(role in user_roles for role in required_roles):
            raise HTTPException(
                status_code=403,
                detail=f"One of roles {required_roles} required"
            )

        return current_user

    return role_checker