# Internal Service-to-Service API endpoints
# UK Management Bot - Auth Service

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from services.auth_service import AuthService
from services.service_token import service_token_manager
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

class ServiceTokenValidationRequest(BaseModel):
    """Request model for service token validation"""
    token: str = Field(..., description="Service token to validate")
    service_name: str = Field(None, description="Expected service name (optional)")

class ServiceTokenValidationResponse(BaseModel):
    """Response model for service token validation"""
    valid: bool = Field(..., description="Whether the token is valid")
    service_name: str = Field(..., description="Name of the validated service")
    permissions: list = Field(default_factory=list, description="List of permissions for this service")
    expires_at: Optional[str] = Field(None, description="Token expiration time")

class ServiceStatsResponse(BaseModel):
    """Response model for user service statistics"""
    total_users: int
    active_users: int
    status_distribution: Dict[str, int]
    role_distribution: Dict[str, int]
    monthly_registrations: int

class ServiceTokenGenerationRequest(BaseModel):
    """Request model for service token generation"""
    service_name: str = Field(..., description="Name of the service requesting token")
    permissions: list = Field(default_factory=list, description="Requested permissions")

@router.post("/validate-service-token", response_model=ServiceTokenValidationResponse)
async def validate_service_token(request: ServiceTokenValidationRequest):
    """
    Validate service-to-service authentication token

    This endpoint validates tokens issued by Auth Service
    Used by other services to validate inter-service communication
    """
    try:
        # Validate the token using service token manager
        token_info = service_token_manager.validate_service_token(
            request.token,
            request.service_name
        )

        if token_info:
            logger.info(f"Service token validated for {token_info.get('service_name')}")

            # Convert Unix timestamp to ISO string
            exp_timestamp = token_info.get("exp")
            expires_at = None
            if exp_timestamp:
                from datetime import datetime
                try:
                    expires_at = datetime.fromtimestamp(exp_timestamp).isoformat() + "Z"
                except (ValueError, TypeError):
                    expires_at = "2025-12-31T23:59:59Z"

            return ServiceTokenValidationResponse(
                valid=True,
                service_name=token_info.get("service_name"),
                permissions=token_info.get("permissions", []),
                expires_at=expires_at or "2025-12-31T23:59:59Z"
            )
        else:
            # Try API key validation as fallback
            api_service = service_token_manager.validate_api_key(request.token)
            if api_service:
                logger.info(f"API key validated for {api_service}")

                return ServiceTokenValidationResponse(
                    valid=True,
                    service_name=api_service,
                    permissions=service_token_manager._get_default_permissions(api_service),
                    expires_at="2024-12-31T23:59:59Z"
                )

        logger.warning("Service token validation failed")
        return ServiceTokenValidationResponse(
            valid=False,
            service_name=request.service_name or "unknown",
            permissions=[],
            expires_at=None
        )

    except Exception as e:
        logger.error(f"Error validating service token: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal error during token validation"
        )

@router.get("/user-stats", response_model=ServiceStatsResponse)
async def get_user_stats_from_user_service():
    """
    Get user statistics from User Service

    Proxy endpoint that fetches statistics from User Service
    Used for admin dashboards and analytics
    """
    try:
        async with get_db() as db:
            auth_service = AuthService(db)

            # Get service token for calling User Service
            service_token = await auth_service._get_service_token()

            # Call User Service internal stats endpoint
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{auth_service.user_service_url}/api/v1/internal/stats/overview",
                    headers={
                        "Authorization": f"Bearer {service_token}",
                        "Content-Type": "application/json"
                    }
                )

                if response.status_code == 200:
                    stats_data = response.json()
                    logger.info("User statistics retrieved from User Service")

                    return ServiceStatsResponse(**stats_data)
                else:
                    logger.error(f"User Service stats error {response.status_code}: {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail="Failed to retrieve user statistics"
                    )

    except httpx.RequestError as e:
        logger.error(f"Failed to connect to User Service: {e}")
        raise HTTPException(
            status_code=503,
            detail="User Service unavailable"
        )
    except Exception as e:
        logger.error(f"Error getting user statistics: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving user statistics"
        )

@router.post("/generate-service-token")
async def generate_service_token(request: ServiceTokenGenerationRequest):
    """
    Generate a new service-to-service authentication token

    Used by services to get tokens for calling other services
    Requires proper authentication and authorization
    """
    try:
        # Generate token using service token manager
        token = service_token_manager.generate_service_token(request.service_name, request.permissions)

        logger.info(f"Generated service token for {request.service_name}")

        return {
            "token": token,
            "service_name": request.service_name,
            "permissions": request.permissions or service_token_manager._get_default_permissions(request.service_name),
            "token_type": "Bearer",
            "expires_in": 30 * 24 * 60 * 60  # 30 days in seconds
        }

    except Exception as e:
        logger.error(f"Error generating service token: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error generating service token"
        )