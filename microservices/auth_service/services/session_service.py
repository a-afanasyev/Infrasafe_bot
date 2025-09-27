# Session Management Service
# UK Management Bot - Auth Service

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import selectinload

from models.auth import Session
from schemas.auth import SessionCreate, SessionResponse
from config import settings

logger = logging.getLogger(__name__)

class SessionService:
    """Service for managing user sessions"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_session(self, session_data: Dict[str, Any]) -> SessionResponse:
        """Create new user session"""
        try:
            # Generate unique session ID
            session_id = secrets.token_urlsafe(32)

            # Calculate expiration times
            session_expires = datetime.now(timezone.utc) + timedelta(hours=settings.session_expire_hours)
            refresh_expires = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_expire_days)

            # Check for existing active sessions and limit them
            await self._cleanup_excess_sessions(session_data["user_id"])

            # Create session record
            session = Session(
                session_id=session_id,
                user_id=session_data["user_id"],
                telegram_id=session_data["telegram_id"],
                access_token="",  # Will be updated after token generation
                refresh_token="",  # Will be updated after token generation
                expires_at=session_expires,
                refresh_expires_at=refresh_expires,
                device_info=session_data.get("device_info"),
                ip_address=session_data.get("ip_address"),
                user_agent=session_data.get("user_agent"),
                is_active=True
            )

            self.db.add(session)
            await self.db.commit()
            await self.db.refresh(session)

            logger.info(f"Created session {session_id} for user {session_data['user_id']}")

            return SessionResponse.model_validate(session)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating session: {e}")
            raise Exception("Could not create session")

    async def get_session(self, session_id: str) -> Optional[SessionResponse]:
        """Get session by ID"""
        try:
            result = await self.db.execute(
                select(Session).where(Session.session_id == session_id)
            )
            session = result.scalar_one_or_none()

            if session:
                return SessionResponse.model_validate(session)
            return None

        except Exception as e:
            logger.error(f"Error getting session {session_id}: {e}")
            return None

    async def update_session_tokens(self, session_id: str, access_token: str, refresh_token: str) -> bool:
        """Update session with new tokens"""
        try:
            result = await self.db.execute(
                update(Session)
                .where(Session.session_id == session_id)
                .values(
                    access_token=access_token,
                    refresh_token=refresh_token,
                    last_activity=datetime.now(timezone.utc)
                )
            )

            await self.db.commit()
            return result.rowcount > 0

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating session tokens {session_id}: {e}")
            return False

    async def update_last_activity(self, session_id: str) -> bool:
        """Update session last activity timestamp"""
        try:
            result = await self.db.execute(
                update(Session)
                .where(Session.session_id == session_id)
                .where(Session.is_active == True)
                .values(last_activity=datetime.now(timezone.utc))
            )

            await self.db.commit()
            return result.rowcount > 0

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating last activity for session {session_id}: {e}")
            return False

    async def deactivate_session(self, session_id: str) -> bool:
        """Deactivate specific session"""
        try:
            result = await self.db.execute(
                update(Session)
                .where(Session.session_id == session_id)
                .values(is_active=False)
            )

            await self.db.commit()
            logger.info(f"Deactivated session {session_id}")
            return result.rowcount > 0

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deactivating session {session_id}: {e}")
            return False

    async def deactivate_all_user_sessions(self, user_id: int, except_session_id: Optional[str] = None) -> int:
        """Deactivate all sessions for a user"""
        try:
            query = update(Session).where(Session.user_id == user_id).values(is_active=False)

            if except_session_id:
                query = query.where(Session.session_id != except_session_id)

            result = await self.db.execute(query)
            await self.db.commit()

            count = result.rowcount
            logger.info(f"Deactivated {count} sessions for user {user_id}")
            return count

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error deactivating user sessions {user_id}: {e}")
            return 0

    async def get_user_sessions(self, user_id: int, active_only: bool = True) -> List[SessionResponse]:
        """Get all sessions for a user"""
        try:
            query = select(Session).where(Session.user_id == user_id)

            if active_only:
                query = query.where(Session.is_active == True)

            query = query.order_by(Session.created_at.desc())

            result = await self.db.execute(query)
            sessions = result.scalars().all()

            return [SessionResponse.model_validate(session) for session in sessions]

        except Exception as e:
            logger.error(f"Error getting user sessions {user_id}: {e}")
            return []

    async def update_session(self, session_id: str, update_data: Dict[str, Any]) -> Optional[SessionResponse]:
        """Update session with provided data"""
        try:
            result = await self.db.execute(
                update(Session)
                .where(Session.session_id == session_id)
                .values(**update_data)
            )

            await self.db.commit()

            if result.rowcount > 0:
                return await self.get_session(session_id)
            return None

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating session {session_id}: {e}")
            return None

    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions"""
        try:
            current_time = datetime.now(timezone.utc)

            # Deactivate sessions that are past their expiration time
            result = await self.db.execute(
                update(Session)
                .where(Session.expires_at < current_time)
                .where(Session.is_active == True)
                .values(is_active=False)
            )

            await self.db.commit()
            count = result.rowcount

            logger.info(f"Cleaned up {count} expired sessions")
            return count

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error cleaning up expired sessions: {e}")
            return 0

    async def _cleanup_excess_sessions(self, user_id: int):
        """Clean up excess sessions if user has too many active sessions"""
        try:
            # Get count of active sessions
            result = await self.db.execute(
                select(func.count(Session.session_id))
                .where(Session.user_id == user_id)
                .where(Session.is_active == True)
            )
            active_count = result.scalar()

            if active_count >= settings.max_sessions_per_user:
                # Get oldest sessions to deactivate
                oldest_sessions = await self.db.execute(
                    select(Session.session_id)
                    .where(Session.user_id == user_id)
                    .where(Session.is_active == True)
                    .order_by(Session.last_activity.asc())
                    .limit(active_count - settings.max_sessions_per_user + 1)
                )

                session_ids_to_deactivate = [row[0] for row in oldest_sessions]

                if session_ids_to_deactivate:
                    await self.db.execute(
                        update(Session)
                        .where(Session.session_id.in_(session_ids_to_deactivate))
                        .values(is_active=False)
                    )

                    logger.info(f"Deactivated {len(session_ids_to_deactivate)} excess sessions for user {user_id}")

        except Exception as e:
            logger.error(f"Error cleaning up excess sessions for user {user_id}: {e}")

    async def get_session_stats(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Get session statistics"""
        try:
            query = select(func.count(Session.session_id)).where(Session.is_active == True)

            if user_id:
                query = query.where(Session.user_id == user_id)

            result = await self.db.execute(query)
            active_sessions = result.scalar()

            # Get total sessions
            total_query = select(func.count(Session.session_id))
            if user_id:
                total_query = total_query.where(Session.user_id == user_id)

            result = await self.db.execute(total_query)
            total_sessions = result.scalar()

            return {
                "active_sessions": active_sessions,
                "total_sessions": total_sessions,
                "user_id": user_id
            }

        except Exception as e:
            logger.error(f"Error getting session stats: {e}")
            return {"active_sessions": 0, "total_sessions": 0, "user_id": user_id}