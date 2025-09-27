# Role Management API endpoints
# UK Management Bot - User Service

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.user import (
    UserRoleMappingCreate, UserRoleMappingUpdate, UserRoleMappingResponse
)
from services.role_service import RoleService

logger = logging.getLogger(__name__)
router = APIRouter()

def get_role_service(db: AsyncSession = Depends(get_db)) -> RoleService:
    return RoleService(db)

@router.get("/{user_id}/roles", response_model=List[UserRoleMappingResponse])
async def get_user_roles(
    user_id: int,
    active_only: bool = True,
    role_service: RoleService = Depends(get_role_service)
):
    """
    Get user roles
    """
    try:
        roles = await role_service.get_user_roles(user_id, active_only)
        return roles
    except Exception as e:
        logger.error(f"Get user roles error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{user_id}/roles", response_model=UserRoleMappingResponse)
async def assign_user_role(
    user_id: int,
    role_data: UserRoleMappingCreate,
    role_service: RoleService = Depends(get_role_service)
):
    """
    Assign role to user
    """
    try:
        role = await role_service.assign_role(user_id, role_data)
        return role
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Assign user role error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.put("/{user_id}/roles/{role_id}", response_model=UserRoleMappingResponse)
async def update_user_role(
    user_id: int,
    role_id: int,
    role_update: UserRoleMappingUpdate,
    role_service: RoleService = Depends(get_role_service)
):
    """
    Update user role
    """
    try:
        role = await role_service.update_role(user_id, role_id, role_update.model_dump(exclude_unset=True))
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        return role
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update user role error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/{user_id}/roles/{role_id}")
async def remove_user_role(
    user_id: int,
    role_id: int,
    role_service: RoleService = Depends(get_role_service)
):
    """
    Remove role from user
    """
    try:
        success = await role_service.remove_role(user_id, role_id)
        if not success:
            raise HTTPException(status_code=404, detail="Role not found")

        return {"message": "Role removed successfully", "user_id": user_id, "role_id": role_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remove user role error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{user_id}/active-role")
async def set_active_role(
    user_id: int,
    role_key: str,
    role_service: RoleService = Depends(get_role_service)
):
    """
    Set user's active role
    """
    try:
        success = await role_service.set_active_role(user_id, role_key)
        if not success:
            raise HTTPException(status_code=404, detail="Role not found")

        return {"message": f"Active role set to {role_key}", "user_id": user_id, "active_role": role_key}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Set active role error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{user_id}/active-role")
async def get_active_role(
    user_id: int,
    role_service: RoleService = Depends(get_role_service)
):
    """
    Get user's active role
    """
    try:
        active_role = await role_service.get_active_role(user_id)
        return {"user_id": user_id, "active_role": active_role}
    except Exception as e:
        logger.error(f"Get active role error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{user_id}/sync-auth")
async def sync_with_auth_service(
    user_id: int,
    role_service: RoleService = Depends(get_role_service)
):
    """
    Synchronize user roles with Auth Service
    """
    try:
        success = await role_service.sync_with_auth_service(user_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to sync with Auth Service")

        return {"message": "Roles synchronized with Auth Service", "user_id": user_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync with auth service error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/bulk/by-role/{role_key}")
async def get_users_by_role(
    role_key: str,
    active_only: bool = True,
    limit: int = 100,
    role_service: RoleService = Depends(get_role_service)
):
    """
    Get all users with specific role
    """
    try:
        users = await role_service.get_users_by_role(role_key, active_only, limit)
        return {"role_key": role_key, "users": users, "count": len(users)}
    except Exception as e:
        logger.error(f"Get users by role error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/stats/distribution")
async def get_role_distribution(
    role_service: RoleService = Depends(get_role_service)
):
    """
    Get role distribution statistics
    """
    try:
        stats = await role_service.get_role_distribution()
        return stats
    except Exception as e:
        logger.error(f"Get role distribution error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")