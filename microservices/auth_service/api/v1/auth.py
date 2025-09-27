# Authentication API endpoints
# UK Management Bot - Auth Service

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.auth import LoginRequest, AuthResponse, TokenRefresh, TokenResponse, LogoutRequest
from services.auth_service import AuthService
from services.session_service import SessionService
from services.jwt_service import JWTService
from services.audit_service import AuditService

logger = logging.getLogger(__name__)
router = APIRouter()

# Dependencies
def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(db)

def get_session_service(db: AsyncSession = Depends(get_db)) -> SessionService:
    return SessionService(db)

def get_jwt_service() -> JWTService:
    return JWTService()

def get_audit_service(db: AsyncSession = Depends(get_db)) -> AuditService:
    return AuditService(db)

@router.post("/login", response_model=AuthResponse)
async def login(
    login_data: LoginRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    session_service: SessionService = Depends(get_session_service),
    jwt_service: JWTService = Depends(get_jwt_service),
    audit_service: AuditService = Depends(get_audit_service)
):
    """
    Login user and create session
    """
    try:
        # Get client info
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")

        # Authenticate user (check if exists in User Service)
        user_data = await auth_service.authenticate_user(login_data.telegram_id)

        if not user_data:
            await audit_service.log_auth_event(
                user_id=None,
                telegram_id=login_data.telegram_id,
                event_type="login",
                event_status="failure",
                event_message="User not found",
                ip_address=client_ip,
                user_agent=user_agent
            )
            raise HTTPException(status_code=401, detail="User not found")

        # Create session
        session_data = {
            **login_data.dict(),
            "user_id": user_data["user_id"],
            "ip_address": client_ip,
            "user_agent": user_agent
        }

        session = await session_service.create_session(session_data)

        # Generate tokens
        token_payload = {
            "user_id": user_data["user_id"],
            "telegram_id": login_data.telegram_id,
            "session_id": session.session_id,
            "roles": user_data.get("roles", [])
        }

        tokens = jwt_service.create_tokens(token_payload)

        # Update session with tokens
        await session_service.update_session_tokens(
            session.session_id,
            tokens.access_token,
            tokens.refresh_token
        )

        # Log successful login
        await audit_service.log_auth_event(
            user_id=user_data["user_id"],
            telegram_id=login_data.telegram_id,
            event_type="login",
            event_status="success",
            event_message="User logged in successfully",
            ip_address=client_ip,
            user_agent=user_agent,
            session_id=session.session_id
        )

        return AuthResponse(
            success=True,
            message="Login successful",
            user_id=user_data["user_id"],
            session=session,
            tokens=tokens
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        await audit_service.log_auth_event(
            user_id=None,
            telegram_id=login_data.telegram_id,
            event_type="login",
            event_status="error",
            event_message=str(e),
            ip_address=client_ip,
            user_agent=user_agent
        )
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_data: TokenRefresh,
    request: Request,
    session_service: SessionService = Depends(get_session_service),
    jwt_service: JWTService = Depends(get_jwt_service),
    audit_service: AuditService = Depends(get_audit_service)
):
    """
    Refresh access token using refresh token
    """
    try:
        # Validate refresh token
        payload = jwt_service.validate_refresh_token(refresh_data.refresh_token)

        # Get active session
        session = await session_service.get_session(payload["session_id"])
        if not session or not session.is_active:
            raise HTTPException(status_code=401, detail="Invalid session")

        # Check refresh token match
        if session.refresh_token != refresh_data.refresh_token:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        # Generate new tokens
        new_tokens = jwt_service.create_tokens(payload)

        # Update session with new tokens
        await session_service.update_session_tokens(
            session.session_id,
            new_tokens.access_token,
            new_tokens.refresh_token
        )

        # Log token refresh
        await audit_service.log_auth_event(
            user_id=payload["user_id"],
            telegram_id=payload["telegram_id"],
            event_type="token_refresh",
            event_status="success",
            session_id=session.session_id
        )

        return new_tokens

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(status_code=401, detail="Invalid refresh token")

@router.post("/logout", response_model=AuthResponse)
async def logout(
    logout_data: LogoutRequest,
    request: Request,
    session_service: SessionService = Depends(get_session_service),
    audit_service: AuditService = Depends(get_audit_service)
):
    """
    Logout user and invalidate session(s)
    """
    try:
        # Get authorization header for current session
        auth_header = request.headers.get("Authorization")
        current_session_id = None

        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            jwt_service = JWTService()
            try:
                payload = jwt_service.validate_access_token(token)
                current_session_id = payload.get("session_id")
            except:
                pass

        if logout_data.all_sessions:
            # Logout from all sessions
            if not current_session_id:
                raise HTTPException(status_code=401, detail="Authentication required")

            session = await session_service.get_session(current_session_id)
            if not session:
                raise HTTPException(status_code=401, detail="Invalid session")

            await session_service.deactivate_all_user_sessions(session.user_id)

            await audit_service.log_auth_event(
                user_id=session.user_id,
                telegram_id=session.telegram_id,
                event_type="logout",
                event_status="success",
                event_message="Logged out from all sessions",
                session_id=current_session_id
            )

            return AuthResponse(
                success=True,
                message="Logged out from all sessions"
            )
        else:
            # Logout from specific session
            session_id = logout_data.session_id or current_session_id
            if not session_id:
                raise HTTPException(status_code=400, detail="Session ID required")

            session = await session_service.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            await session_service.deactivate_session(session_id)

            await audit_service.log_auth_event(
                user_id=session.user_id,
                telegram_id=session.telegram_id,
                event_type="logout",
                event_status="success",
                event_message="Logged out from session",
                session_id=session_id
            )

            return AuthResponse(
                success=True,
                message="Logged out successfully"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/me")
async def get_current_user(
    request: Request,
    jwt_service: JWTService = Depends(get_jwt_service),
    session_service: SessionService = Depends(get_session_service)
):
    """
    Get current user information from token
    """
    try:
        # Get and validate token
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authentication required")

        token = auth_header[7:]
        payload = jwt_service.validate_access_token(token)

        # Verify session is still active
        session = await session_service.get_session(payload["session_id"])
        if not session or not session.is_active:
            raise HTTPException(status_code=401, detail="Session expired")

        # Update last activity
        await session_service.update_last_activity(session.session_id)

        return {
            "user_id": payload["user_id"],
            "telegram_id": payload["telegram_id"],
            "roles": payload.get("roles", []),
            "session_id": payload["session_id"],
            "session_expires_at": session.expires_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get current user error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")