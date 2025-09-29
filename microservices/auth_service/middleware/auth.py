# Authentication Middleware and Dependencies
# UK Management Bot - Auth Service

import logging
from typing import Dict, Any, Optional

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from services.jwt_service import JWTService
from services.session_service import SessionService
from database import get_db
from config import settings

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

async def require_service_auth(request: Request) -> str:
    """
    Secure service authentication using centralized HMAC validation

    SECURITY IMPROVEMENTS:
    - No hardcoded API keys in code
    - HMAC-based validation instead of plain string comparison
    - Centralized revocation checking via Redis
    - Audit logging for all authentication attempts
    """
    from services.static_key_service import static_key_service

    service_name = request.headers.get("X-Service-Name")
    service_api_key = request.headers.get("X-Service-API-Key")

    if not service_name or not service_api_key:
        logger.warning("Service authentication failed: missing headers")
        raise HTTPException(
            status_code=401,
            detail="Service authentication required: X-Service-Name and X-Service-API-Key headers required"
        )

    # Extract request info for audit logging
    request_info = {
        "client_ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent")
    }

    try:
        # Use centralized HMAC-based validation
        service_credentials = await static_key_service.validate_service_credentials(
            service_name=service_name,
            api_key=service_api_key,
            request_info=request_info
        )

        if service_credentials and service_name in settings.service_allowlist:
            return service_name
        else:
            logger.warning(f"Service authentication failed for: {service_name}")
            raise HTTPException(
                status_code=401,
                detail="Invalid service credentials or service not allowed"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Service authentication error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Authentication service error"
        )

async def require_admin_or_service_auth(request: Request) -> Dict[str, Any]:
    """
    Dependency that accepts either admin JWT or service API key
    Returns auth info with type (admin|service) and details
    """
    # Try service API key first
    service_api_key = request.headers.get("X-Service-API-Key")

    if service_api_key:
        try:
            service_name = await require_service_auth(request)
            return {
                "type": "service",
                "service_name": service_name,
                "authenticated": True
            }
        except HTTPException:
            pass  # Fall through to JWT auth

    # Try admin JWT auth
    try:
        # Get auth header manually since we can't use get_current_user dependency here
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="No valid auth found")

        token = auth_header.split(" ")[1]

        # Use JWT service to validate token
        jwt_service = JWTService()
        payload = jwt_service.validate_access_token(token)
        user_roles = payload.get("roles", [])

        if not any(role in ["admin", "superadmin"] for role in user_roles):
            raise HTTPException(status_code=403, detail="Admin access required")

        return {
            "type": "admin",
            "user": payload,
            "authenticated": True
        }
    except (HTTPException, Exception):
        pass

    # Neither authentication method worked
    raise HTTPException(
        status_code=401,
        detail="Admin JWT token or service API key required"
    )

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