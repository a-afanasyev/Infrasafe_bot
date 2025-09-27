# Session Management API endpoints
# UK Management Bot - Auth Service

import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.auth import SessionResponse, SessionUpdate
from services.session_service import SessionService
from middleware.auth import require_auth

logger = logging.getLogger(__name__)
router = APIRouter()

def get_session_service(db: AsyncSession = Depends(get_db)) -> SessionService:
    return SessionService(db)

@router.get("/", response_model=List[SessionResponse])
async def get_user_sessions(
    user_data: dict = Depends(require_auth),
    session_service: SessionService = Depends(get_session_service),
    active_only: bool = Query(True, description="Filter only active sessions")
):
    """
    Get all sessions for authenticated user
    """
    try:
        sessions = await session_service.get_user_sessions(
            user_data["user_id"],
            active_only=active_only
        )
        return sessions
    except Exception as e:
        logger.error(f"Get user sessions error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    user_data: dict = Depends(require_auth),
    session_service: SessionService = Depends(get_session_service)
):
    """
    Get specific session by ID
    """
    try:
        session = await session_service.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Verify session belongs to authenticated user
        if session.user_id != user_data["user_id"]:
            raise HTTPException(status_code=403, detail="Access denied")

        return session
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get session error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    session_update: SessionUpdate,
    user_data: dict = Depends(require_auth),
    session_service: SessionService = Depends(get_session_service)
):
    """
    Update session (e.g., deactivate)
    """
    try:
        # Get existing session
        session = await session_service.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Verify session belongs to authenticated user
        if session.user_id != user_data["user_id"]:
            raise HTTPException(status_code=403, detail="Access denied")

        # Update session
        updated_session = await session_service.update_session(session_id, session_update.dict(exclude_unset=True))

        return updated_session
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update session error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/{session_id}")
async def deactivate_session(
    session_id: str,
    user_data: dict = Depends(require_auth),
    session_service: SessionService = Depends(get_session_service)
):
    """
    Deactivate (logout) specific session
    """
    try:
        # Get existing session
        session = await session_service.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Verify session belongs to authenticated user or user is admin
        if session.user_id != user_data["user_id"] and "admin" not in user_data.get("roles", []):
            raise HTTPException(status_code=403, detail="Access denied")

        # Deactivate session
        await session_service.deactivate_session(session_id)

        return {"message": "Session deactivated successfully", "session_id": session_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Deactivate session error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/")
async def deactivate_all_sessions(
    user_data: dict = Depends(require_auth),
    session_service: SessionService = Depends(get_session_service),
    except_current: bool = Query(True, description="Keep current session active")
):
    """
    Deactivate all user sessions
    """
    try:
        current_session_id = user_data.get("session_id") if except_current else None

        count = await session_service.deactivate_all_user_sessions(
            user_data["user_id"],
            except_session_id=current_session_id
        )

        return {
            "message": f"Deactivated {count} sessions",
            "deactivated_count": count,
            "current_session_preserved": except_current
        }
    except Exception as e:
        logger.error(f"Deactivate all sessions error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/cleanup/expired")
async def cleanup_expired_sessions(
    user_data: dict = Depends(require_auth),
    session_service: SessionService = Depends(get_session_service)
):
    """
    Cleanup expired sessions (admin only)
    """
    try:
        # Check admin permissions
        if "admin" not in user_data.get("roles", []):
            raise HTTPException(status_code=403, detail="Admin access required")

        count = await session_service.cleanup_expired_sessions()

        return {
            "message": f"Cleaned up {count} expired sessions",
            "cleaned_count": count,
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cleanup expired sessions error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")