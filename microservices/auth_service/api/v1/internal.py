# Internal Service-to-Service API endpoints
# UK Management Bot - Auth Service

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from services.auth_service import AuthService
from services.service_token import service_token_manager
from database import get_db
from middleware.auth import require_admin

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
            api_service = await service_token_manager.validate_api_key(request.token)
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

            # Get service auth headers for calling User Service
            auth_headers = auth_service._get_service_auth_headers()

            # Call User Service internal stats endpoint
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{auth_service.user_service_url}/api/v1/internal/stats/overview",
                    headers=auth_headers
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

from middleware.auth import require_admin

@router.post("/generate-service-token")
async def generate_service_token_disabled(
    token_request: ServiceTokenGenerationRequest,
    admin_user: dict = Depends(require_admin)
):
    """
    SECURITY: Service token generation DISABLED

    This endpoint has been permanently disabled to prevent JWT token generation.
    Services now use static API key authentication via X-Service-API-Key headers
    instead of self-minting JWT tokens.

    This elimination of JWT token generation removes the security vulnerability
    where services could mint tokens for other services with arbitrary permissions.
    """
    logger.warning(
        f"Admin {admin_user.get('user_id')} attempted to generate service token for {token_request.service_name} "
        f"- endpoint disabled for security"
    )

    raise HTTPException(
        status_code=410,  # Gone - resource no longer available
        detail="Service token generation disabled. Services use static API key authentication instead."
    )

@router.post("/validate-service-credentials")
async def validate_service_credentials(request: Request):
    """
    Centralized service credentials validation with HMAC security

    This endpoint provides secure validation of service API keys using:
    - HMAC-based key verification (not plain string comparison)
    - Revocation checking via Redis
    - Audit logging for security events
    - Centralized permissions management
    """
    from services.static_key_service import static_key_service

    try:
        service_name = request.headers.get("X-Service-Name")
        service_api_key = request.headers.get("X-Service-API-Key")

        # Extract request info for audit logging
        request_info = {
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent")
        }

        if not service_name or not service_api_key:
            return ServiceTokenValidationResponse(
                valid=False,
                service_name="unknown",
                permissions=[],
                expires_at=None
            )

        # Validate using secure HMAC-based service
        service_credentials = await static_key_service.validate_service_credentials(
            service_name=service_name,
            api_key=service_api_key,
            request_info=request_info
        )

        if service_credentials:
            return ServiceTokenValidationResponse(
                valid=True,
                service_name=service_credentials.service_name,
                permissions=service_credentials.permissions,
                expires_at="2026-12-31T23:59:59Z"  # Static credentials have long lifetime
            )
        else:
            return ServiceTokenValidationResponse(
                valid=False,
                service_name="unknown",
                permissions=[],
                expires_at=None
            )

    except Exception as e:
        logger.error(f"Error validating service credentials: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal error during credentials validation"
        )


@router.post("/revoke-service")
async def revoke_service_credentials(
    revocation_request: dict,
    admin_user: dict = Depends(require_admin)
):
    """
    Revoke service credentials with immediate effect

    SECURITY: Only admins can revoke service credentials.
    Revoked services will fail authentication immediately across all instances.
    """
    from services.static_key_service import static_key_service

    try:
        service_name = revocation_request.get("service_name")
        reason = revocation_request.get("reason", "Administrative revocation")

        if not service_name:
            raise HTTPException(
                status_code=400,
                detail="service_name is required"
            )

        admin_user_id = admin_user.get("user_id", "unknown")

        success = await static_key_service.revoke_service(
            service_name=service_name,
            reason=reason,
            admin_user_id=admin_user_id
        )

        if success:
            return {
                "success": True,
                "service_name": service_name,
                "message": f"Service {service_name} credentials revoked",
                "revoked_by": admin_user_id,
                "reason": reason
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to revoke service credentials"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking service credentials: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal error during revocation"
        )


@router.post("/restore-service")
async def restore_service_credentials(
    restoration_request: dict,
    admin_user: dict = Depends(require_admin)
):
    """
    Restore previously revoked service credentials

    SECURITY: Only admins can restore service credentials.
    """
    from services.static_key_service import static_key_service

    try:
        service_name = restoration_request.get("service_name")

        if not service_name:
            raise HTTPException(
                status_code=400,
                detail="service_name is required"
            )

        admin_user_id = admin_user.get("user_id", "unknown")

        success = await static_key_service.restore_service(
            service_name=service_name,
            admin_user_id=admin_user_id
        )

        if success:
            return {
                "success": True,
                "service_name": service_name,
                "message": f"Service {service_name} credentials restored",
                "restored_by": admin_user_id
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to restore service credentials"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restoring service credentials: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal error during restoration"
        )


@router.get("/service-status")
async def get_service_status(admin_user: dict = Depends(require_admin)):
    """
    Get status of all registered services

    SECURITY: Only admins can view service status.
    Shows revocation status, last used timestamps, and permissions.
    """
    from services.static_key_service import static_key_service

    try:
        service_status = await static_key_service.get_service_status()

        return {
            "success": True,
            "services": service_status,
            "total_services": len(service_status),
            "requested_by": admin_user.get("user_id", "unknown")
        }

    except Exception as e:
        logger.error(f"Error getting service status: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal error getting service status"
        )


@router.get("/auth-audit")
async def get_auth_audit_logs(
    hours: int = 24,
    admin_user: dict = Depends(require_admin)
):
    """
    Get authentication audit logs

    SECURITY: Only admins can view audit logs.
    Shows recent authentication attempts, successes, failures, and security events.
    """
    from services.static_key_service import static_key_service

    try:
        if hours < 1 or hours > 168:  # Max 1 week
            raise HTTPException(
                status_code=400,
                detail="hours must be between 1 and 168 (1 week)"
            )

        audit_logs = await static_key_service.get_auth_audit_logs(hours=hours)

        return {
            "success": True,
            "audit_logs": audit_logs,
            "hours": hours,
            "total_events": len(audit_logs),
            "requested_by": admin_user.get("user_id", "unknown")
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting audit logs: {e}")
        raise HTTPException(
            status_code=500,
            detail="Internal error getting audit logs"
        )