# Internal Service-to-Service API endpoints
# UK Management Bot - User Service

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from config import settings
from middleware.service_auth import require_service_auth, require_specific_service
from services.user_service import UserService
from database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()

# Dependency for UserService
def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)

class ServiceTokenValidation(BaseModel):
    """Request model for service token validation"""
    token: str = Field(..., description="Service token to validate")
    service_name: str = Field(..., description="Name of the service requesting validation")

class ServiceTokenResponse(BaseModel):
    """Response model for service token validation"""
    valid: bool = Field(..., description="Whether the token is valid")
    service_name: str = Field(..., description="Name of the validated service")
    permissions: list = Field(default_factory=list, description="List of permissions for this service")
    expires_at: str = Field(None, description="Token expiration time")

class ServiceStatsResponse(BaseModel):
    """Response model for service statistics"""
    total_users: int
    active_users: int
    status_distribution: Dict[str, int]
    role_distribution: Dict[str, int]
    monthly_registrations: int

@router.post("/validate-service-token", response_model=ServiceTokenResponse)
async def validate_service_token(
    request: ServiceTokenValidation,
    _: Dict[str, Any] = Depends(require_service_auth)
):
    """
    Validate service-to-service authentication token

    This endpoint is called by other services to validate tokens
    Used primarily by Auth Service for inter-service communication
    """
    try:
        # Simple validation logic for now
        # In production, this would use the same JWT validation as Auth Service

        # Check if service is in allowed list
        if request.service_name not in settings.allowed_services:
            logger.warning(f"Service not in allowed list: {request.service_name}")
            return ServiceTokenResponse(
                valid=False,
                service_name=request.service_name,
                permissions=[],
                expires_at=None
            )

        # For development, accept any non-empty token for allowed services
        if request.token and len(request.token) > 0:

            # Define permissions based on service
            service_permissions = {
                "auth-service": ["read_users", "write_users", "read_roles"],
                "request-service": ["read_users", "read_roles"],
                "shift-service": ["read_users", "read_roles"],
                "notification-service": ["read_users"],
                "analytics-service": ["read_users", "read_roles"],
                "ai-service": ["read_users", "read_roles"]
            }

            permissions = service_permissions.get(request.service_name, ["read_users"])

            logger.info(f"Service token validated for {request.service_name}")

            return ServiceTokenResponse(
                valid=True,
                service_name=request.service_name,
                permissions=permissions,
                expires_at="2024-12-31T23:59:59Z"  # Mock expiration
            )

        return ServiceTokenResponse(
            valid=False,
            service_name=request.service_name,
            permissions=[],
            expires_at=None
        )

    except Exception as e:
        logger.error(f"Error validating service token: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal error during token validation"
        )

@router.get("/stats/overview", response_model=ServiceStatsResponse)
async def get_user_statistics(
    service_info: Dict[str, Any] = Depends(require_service_auth)
):
    """
    Get user statistics overview

    Used by Auth Service for admin endpoints and analytics
    Requires service authentication
    """
    try:
        # Get statistics from user service
        from database import get_db
        async with get_db() as db:
            from services.user_service import UserService
            user_service_instance = UserService(db)
            stats = await user_service_instance.get_user_stats()

        logger.info(f"User statistics requested by {service_info.get('service_name', 'unknown')}")

        # Return stats directly (UserStatsResponse has same structure as ServiceStatsResponse)
        return ServiceStatsResponse(
            total_users=stats.total_users,
            active_users=stats.active_users,
            status_distribution=stats.status_distribution,
            role_distribution=stats.role_distribution,
            monthly_registrations=stats.monthly_registrations
        )

    except Exception as e:
        logger.error(f"Error getting user statistics: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving user statistics"
        )

@router.get("/health/dependencies")
async def check_service_dependencies(
    _: Dict[str, Any] = Depends(require_service_auth)
):
    """
    Check health of service dependencies

    Used by other services to verify User Service connectivity
    """
    try:
        # Check database connection
        from database import check_database_connection
        db_health = await check_database_connection()

        health_status = {
            "service": settings.service_name,
            "status": "healthy" if db_health["status"] == "healthy" else "unhealthy",
            "dependencies": {
                "database": {
                    "status": db_health["status"],
                    "type": "PostgreSQL",
                    "pool_size": db_health.get("engine_pool_size", 0),
                    "checked_out": db_health.get("engine_checked_out", 0)
                },
                "redis": {
                    "status": "healthy",  # TODO: Add Redis health check
                    "type": "Redis"
                }
            },
            "integrations": {
                "auth_service": settings.auth_service_url,
                "media_service": settings.media_service_url,
                "notification_service": settings.notification_service_url
            }
        }

        return health_status

    except Exception as e:
        logger.error(f"Error checking service dependencies: {e}")
        raise HTTPException(
            status_code=503,
            detail="Service dependency check failed"
        )


# Bot Gateway Integration Endpoints

@router.get("/users/telegram/{telegram_id}")
async def get_user_by_telegram_id(
    telegram_id: int,
    user_service: UserService = Depends(get_user_service)
):
    """
    Get user by Telegram ID (for Bot Gateway).

    TODO: Re-enable service auth after fixing FastAPI dependency injection

    Args:
        telegram_id: Telegram user ID
        user_service: UserService instance

    Returns:
        User object if found

    Raises:
        HTTPException: 404 if user not found
    """
    try:
        service = user_service
        user = await service.get_user_by_telegram_id(telegram_id)

        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User with telegram_id={telegram_id} not found"
            )

        logger.info(f"Retrieved user {user.id} by telegram_id={telegram_id}")

        # Convert UserFullResponse to simple dict for Bot Gateway
        return {
            "id": str(user.id),
            "telegram_id": user.telegram_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone_number": user.phone,
            "language_code": user.language_code or "ru",
            "role": user.roles[0].role_key if user.roles else None,
            "status": user.status,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user by telegram_id: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal error getting user"
        )


class InternalUserCreateRequest(BaseModel):
    """Request model for internal user creation"""
    telegram_id: int = Field(..., description="Telegram user ID")
    username: str = Field(None, description="Telegram username")
    first_name: str = Field(None, description="First name")
    last_name: str = Field(None, description="Last name")
    phone_number: str = Field(None, description="Phone number")
    language_code: str = Field(default="ru", description="Language code")


@router.post("/users")
async def create_user_internal(
    request: InternalUserCreateRequest,
    user_service: UserService = Depends(get_user_service)
):
    """
    Create user (for Bot Gateway).

    TODO: Re-enable service auth after fixing FastAPI dependency injection

    Args:
        request: User creation data
        user_service: UserService instance

    Returns:
        Created user object

    Raises:
        HTTPException: 400 if user already exists or validation error
    """
    try:
        service = user_service

        # Check if user already exists
        existing_user = await service.get_user_by_telegram_id(request.telegram_id)
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail=f"User with telegram_id={request.telegram_id} already exists"
            )

        # Create new user
        from schemas.user import UserCreate
        user_data = UserCreate(
            telegram_id=request.telegram_id,
            username=request.username,
            first_name=request.first_name,
            last_name=request.last_name,
            phone_number=request.phone_number,
            language_code=request.language_code or "ru"
        )
        user = await service.create_user(user_data)

        logger.info(f"Created user {user.id} for telegram_id={request.telegram_id}")

        # Convert UserFullResponse to simple dict for Bot Gateway
        return {
            "id": str(user.id),
            "telegram_id": user.telegram_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone_number": user.phone,
            "language_code": user.language_code or "ru",
            "role": None,  # New users don't have roles yet
            "status": user.status,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error creating user: {e}")
        logger.error(f"Traceback: {error_details}")
        print(f"ERROR creating user: {e}", flush=True)
        print(f"Traceback:\n{error_details}", flush=True)
        raise HTTPException(
            status_code=500,
            detail="Internal error creating user"
        )