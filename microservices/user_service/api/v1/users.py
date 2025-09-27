# User Management API endpoints
# UK Management Bot - User Service

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.user import (
    UserCreate, UserUpdate, UserResponse, UserFullResponse,
    UserListResponse, UserSearchFilters, UserStatsResponse,
    ExecutorResponse, ExecutorListResponse
)
from services.user_service import UserService
from middleware.service_auth import require_specific_service

logger = logging.getLogger(__name__)
router = APIRouter()

def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)

@router.get("/", response_model=UserListResponse)
async def get_users(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    role_key: Optional[str] = Query(None, description="Filter by role"),
    search: Optional[str] = Query(None, description="Search by name or username"),
    user_service: UserService = Depends(get_user_service)
):
    """
    Get paginated list of users with optional filters
    """
    try:
        filters = UserSearchFilters(
            status=status,
            role_key=role_key
        )

        users, total_count = await user_service.get_users_list(
            filters=filters,
            search=search,
            page=page,
            page_size=page_size
        )

        total_pages = (total_count + page_size - 1) // page_size

        return UserListResponse(
            users=users,
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    except Exception as e:
        logger.error(f"Get users error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/", response_model=UserFullResponse)
async def create_user(
    user_data: UserCreate,
    user_service: UserService = Depends(get_user_service)
):
    """
    Create a new user
    """
    try:
        user = await user_service.create_user(user_data)
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Create user error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/by-telegram/{telegram_id}", response_model=UserFullResponse)
async def get_user_by_telegram_id(
    telegram_id: int,
    user_service: UserService = Depends(get_user_service),
    service_info: Dict[str, Any] = Depends(require_specific_service("auth-service"))
):
    """
    Get user by Telegram ID (used by Auth Service)

    This endpoint requires service authentication from the auth-service only.
    Used by Auth Service to verify user credentials during authentication.
    """
    try:
        logger.info(f"Service {service_info['service_name']} requesting user by telegram_id: {telegram_id}")

        user = await user_service.get_user_by_telegram_id(telegram_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        logger.info(f"User found and returned to {service_info['service_name']}")
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user by telegram ID error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{user_id}", response_model=UserFullResponse)
async def get_user(
    user_id: int,
    user_service: UserService = Depends(get_user_service)
):
    """
    Get user by ID
    """
    try:
        user = await user_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.put("/{user_id}", response_model=UserFullResponse)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    user_service: UserService = Depends(get_user_service)
):
    """
    Update user information
    """
    try:
        user = await user_service.update_user(user_id, user_update.model_dump(exclude_unset=True))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update user error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/{user_id}")
async def archive_user(
    user_id: int,
    user_service: UserService = Depends(get_user_service)
):
    """
    Archive user (soft delete)
    """
    try:
        success = await user_service.archive_user(user_id)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")

        return {"message": "User archived successfully", "user_id": user_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Archive user error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.patch("/{user_id}/status")
async def change_user_status(
    user_id: int,
    status: str,
    user_service: UserService = Depends(get_user_service)
):
    """
    Change user status (pending/approved/blocked)
    """
    try:
        if status not in ['pending', 'approved', 'blocked', 'archived']:
            raise HTTPException(status_code=400, detail="Invalid status")

        user = await user_service.change_user_status(user_id, status)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return {"message": f"User status changed to {status}", "user": user}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Change user status error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/search/by-username/{username}", response_model=List[UserResponse])
async def search_users_by_username(
    username: str,
    limit: int = Query(10, ge=1, le=50),
    user_service: UserService = Depends(get_user_service)
):
    """
    Search users by username
    """
    try:
        users = await user_service.search_users_by_username(username, limit)
        return users
    except Exception as e:
        logger.error(f"Search users by username error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/stats/overview", response_model=UserStatsResponse)
async def get_user_statistics(
    user_service: UserService = Depends(get_user_service)
):
    """
    Get user statistics overview
    """
    try:
        stats = await user_service.get_user_stats()
        return stats
    except Exception as e:
        logger.error(f"Get user statistics error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{user_id}/activate")
async def activate_user(
    user_id: int,
    user_service: UserService = Depends(get_user_service)
):
    """
    Activate user account
    """
    try:
        user = await user_service.activate_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return {"message": "User activated successfully", "user": user}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Activate user error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    user_service: UserService = Depends(get_user_service)
):
    """
    Deactivate user account
    """
    try:
        user = await user_service.deactivate_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return {"message": "User deactivated successfully", "user": user}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Deactivate user error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/executors", response_model=ExecutorListResponse)
async def get_executors(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    specialization: Optional[str] = Query(None, description="Filter by specialization"),
    status: Optional[str] = Query("approved", description="Filter by status"),
    availability_status: Optional[str] = Query(None, description="Filter by availability"),
    user_service: UserService = Depends(get_user_service)
):
    """
    Get paginated list of executors with executor-specific information

    This endpoint provides executor-specific data including:
    - Current workload
    - Specializations
    - Availability score
    - Rating

    Designed for Request Service integration and assignment optimization.
    """
    try:
        executors, total_count = await user_service.get_executors_list(
            specialization=specialization,
            status=status,
            availability_status=availability_status,
            page=page,
            page_size=page_size
        )

        total_pages = (total_count + page_size - 1) // page_size

        # Convert to ExecutorResponse objects
        executor_responses = []
        for executor_data in executors:
            executor_responses.append(ExecutorResponse(**executor_data))

        return ExecutorListResponse(
            executors=executor_responses,
            total_count=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    except Exception as e:
        logger.error(f"Get executors error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")