# Permission Management API endpoints
# UK Management Bot - Auth Service

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.auth import (
    PermissionResponse, PermissionCreate, PermissionUpdate,
    UserRoleResponse, UserRoleCreate, UserRoleUpdate,
    PermissionCheck, PermissionCheckResponse
)
from services.permission_service import PermissionService
from middleware.auth import require_auth, require_admin

logger = logging.getLogger(__name__)
router = APIRouter()

def get_permission_service(db: AsyncSession = Depends(get_db)) -> PermissionService:
    return PermissionService(db)

# Permission CRUD endpoints
@router.get("/", response_model=List[PermissionResponse])
async def get_all_permissions(
    user_data: dict = Depends(require_auth),
    permission_service: PermissionService = Depends(get_permission_service),
    service_name: Optional[str] = Query(None, description="Filter by service name"),
    active_only: bool = Query(True, description="Filter only active permissions")
):
    """
    Get all permissions (admin only)
    """
    try:
        # Check admin permissions
        if "admin" not in user_data.get("roles", []):
            raise HTTPException(status_code=403, detail="Admin access required")

        permissions = await permission_service.get_permissions(
            service_name=service_name,
            active_only=active_only
        )
        return permissions
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get permissions error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/", response_model=PermissionResponse)
async def create_permission(
    permission_data: PermissionCreate,
    user_data: dict = Depends(require_admin),
    permission_service: PermissionService = Depends(get_permission_service)
):
    """
    Create new permission (admin only)
    """
    try:
        permission = await permission_service.create_permission(permission_data)
        return permission
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Create permission error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{permission_id}", response_model=PermissionResponse)
async def get_permission(
    permission_id: int,
    user_data: dict = Depends(require_auth),
    permission_service: PermissionService = Depends(get_permission_service)
):
    """
    Get permission by ID (admin only)
    """
    try:
        if "admin" not in user_data.get("roles", []):
            raise HTTPException(status_code=403, detail="Admin access required")

        permission = await permission_service.get_permission(permission_id)
        if not permission:
            raise HTTPException(status_code=404, detail="Permission not found")

        return permission
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get permission error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.patch("/{permission_id}", response_model=PermissionResponse)
async def update_permission(
    permission_id: int,
    permission_update: PermissionUpdate,
    user_data: dict = Depends(require_admin),
    permission_service: PermissionService = Depends(get_permission_service)
):
    """
    Update permission (admin only)
    """
    try:
        permission = await permission_service.update_permission(
            permission_id,
            permission_update.dict(exclude_unset=True)
        )
        if not permission:
            raise HTTPException(status_code=404, detail="Permission not found")

        return permission
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update permission error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# User Role Management
@router.get("/users/{user_id}/roles", response_model=List[UserRoleResponse])
async def get_user_roles(
    user_id: int,
    user_data: dict = Depends(require_auth),
    permission_service: PermissionService = Depends(get_permission_service),
    active_only: bool = Query(True, description="Filter only active roles")
):
    """
    Get user roles (own roles or admin access)
    """
    try:
        # Users can see their own roles, admins can see any user's roles
        if user_id != user_data["user_id"] and "admin" not in user_data.get("roles", []):
            raise HTTPException(status_code=403, detail="Access denied")

        roles = await permission_service.get_user_roles(user_id, active_only=active_only)
        return roles
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user roles error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/users/{user_id}/roles", response_model=UserRoleResponse)
async def assign_user_role(
    user_id: int,
    role_data: UserRoleCreate,
    user_data: dict = Depends(require_admin),
    permission_service: PermissionService = Depends(get_permission_service)
):
    """
    Assign role to user (admin only)
    """
    try:
        # Set assigned_by to current admin user
        role_data_dict = role_data.dict()
        role_data_dict["assigned_by"] = user_data["user_id"]

        role = await permission_service.assign_user_role(user_id, role_data_dict)
        return role
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Assign user role error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.patch("/users/{user_id}/roles/{role_id}", response_model=UserRoleResponse)
async def update_user_role(
    user_id: int,
    role_id: int,
    role_update: UserRoleUpdate,
    user_data: dict = Depends(require_admin),
    permission_service: PermissionService = Depends(get_permission_service)
):
    """
    Update user role (admin only)
    """
    try:
        role = await permission_service.update_user_role(
            user_id,
            role_id,
            role_update.dict(exclude_unset=True)
        )
        if not role:
            raise HTTPException(status_code=404, detail="User role not found")

        return role
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update user role error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/users/{user_id}/roles/{role_id}")
async def remove_user_role(
    user_id: int,
    role_id: int,
    user_data: dict = Depends(require_admin),
    permission_service: PermissionService = Depends(get_permission_service)
):
    """
    Remove role from user (admin only)
    """
    try:
        success = await permission_service.remove_user_role(user_id, role_id)
        if not success:
            raise HTTPException(status_code=404, detail="User role not found")

        return {"message": "Role removed successfully", "user_id": user_id, "role_id": role_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remove user role error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Permission Checking
@router.post("/check", response_model=PermissionCheckResponse)
async def check_user_permission(
    permission_check: PermissionCheck,
    permission_service: PermissionService = Depends(get_permission_service)
):
    """
    Check if user has specific permission (for inter-service calls)
    """
    try:
        result = await permission_service.check_user_permission(
            permission_check.user_id,
            permission_check.telegram_id,
            permission_check.permission_key,
            permission_check.resource_id
        )
        return result
    except Exception as e:
        logger.error(f"Permission check error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/users/{user_id}/permissions")
async def get_user_permissions(
    user_id: int,
    user_data: dict = Depends(require_auth),
    permission_service: PermissionService = Depends(get_permission_service),
    service_name: Optional[str] = Query(None, description="Filter by service name")
):
    """
    Get effective permissions for user
    """
    try:
        # Users can see their own permissions, admins can see any user's permissions
        if user_id != user_data["user_id"] and "admin" not in user_data.get("roles", []):
            raise HTTPException(status_code=403, detail="Access denied")

        permissions = await permission_service.get_user_effective_permissions(
            user_id,
            service_name=service_name
        )

        return {
            "user_id": user_id,
            "permissions": permissions,
            "service_filter": service_name
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user permissions error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Rate Limiting Management
@router.get("/rate-limit/clients")
async def get_rate_limited_clients(
    user_data: dict = Depends(require_admin)
):
    """
    Get all clients currently being rate limited (admin only)
    """
    try:
        from main import app

        # Find the Redis rate limiting middleware
        rate_limit_middleware = None
        for middleware in app.user_middleware:
            if middleware.cls.__name__ == "RedisRateLimitMiddleware":
                rate_limit_middleware = middleware.cls
                break

        if not rate_limit_middleware:
            raise HTTPException(status_code=503, detail="Rate limiting middleware not found")

        # Create a temporary instance to access methods
        temp_instance = rate_limit_middleware(None)
        clients = await temp_instance.get_all_clients()

        return {
            "total_clients": len(clients),
            "clients": clients
        }
    except Exception as e:
        logger.error(f"Get rate limited clients error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/rate-limit/client/{client_ip}")
async def get_client_rate_limit_stats(
    client_ip: str,
    user_data: dict = Depends(require_admin)
):
    """
    Get rate limiting stats for specific client (admin only)
    """
    try:
        from main import app

        # Find the Redis rate limiting middleware
        rate_limit_middleware = None
        for middleware in app.user_middleware:
            if middleware.cls.__name__ == "RedisRateLimitMiddleware":
                rate_limit_middleware = middleware.cls
                break

        if not rate_limit_middleware:
            raise HTTPException(status_code=503, detail="Rate limiting middleware not found")

        # Create a temporary instance to access methods
        temp_instance = rate_limit_middleware(None)
        stats = await temp_instance.get_client_stats(client_ip)

        return stats
    except Exception as e:
        logger.error(f"Get client rate limit stats error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/rate-limit/client/{client_ip}")
async def clear_client_rate_limit(
    client_ip: str,
    user_data: dict = Depends(require_admin)
):
    """
    Clear rate limit for specific client (admin only)
    """
    try:
        from main import app

        # Find the Redis rate limiting middleware
        rate_limit_middleware = None
        for middleware in app.user_middleware:
            if middleware.cls.__name__ == "RedisRateLimitMiddleware":
                rate_limit_middleware = middleware.cls
                break

        if not rate_limit_middleware:
            raise HTTPException(status_code=503, detail="Rate limiting middleware not found")

        # Create a temporary instance to access methods
        temp_instance = rate_limit_middleware(None)
        success = await temp_instance.clear_client_limit(client_ip)

        if success:
            return {"message": f"Rate limit cleared for client {client_ip}"}
        else:
            return {"message": f"No rate limit found for client {client_ip}"}
    except Exception as e:
        logger.error(f"Clear client rate limit error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/rate-limit/cleanup")
async def cleanup_expired_rate_limits(
    user_data: dict = Depends(require_admin)
):
    """
    Manually trigger cleanup of expired rate limit entries (admin only)
    """
    try:
        from main import app

        # Find the Redis rate limiting middleware
        rate_limit_middleware = None
        for middleware in app.user_middleware:
            if middleware.cls.__name__ == "RedisRateLimitMiddleware":
                rate_limit_middleware = middleware.cls
                break

        if not rate_limit_middleware:
            raise HTTPException(status_code=503, detail="Rate limiting middleware not found")

        # Create a temporary instance to access methods
        temp_instance = rate_limit_middleware(None)
        await temp_instance.cleanup_expired_entries()

        return {"message": "Rate limit cleanup completed"}
    except Exception as e:
        logger.error(f"Rate limit cleanup error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# System defaults
@router.post("/initialize-defaults")
async def initialize_default_permissions(
    user_data: dict = Depends(require_admin),
    permission_service: PermissionService = Depends(get_permission_service)
):
    """
    Initialize default system permissions (admin only)
    """
    try:
        count = await permission_service.initialize_default_permissions()

        return {
            "message": f"Initialized {count} default permissions",
            "created_count": count
        }
    except Exception as e:
        logger.error(f"Initialize default permissions error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")