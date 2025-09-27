# Audit Logging Service
# UK Management Bot - Auth Service

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from models.auth import AuthLog
from schemas.auth import AuthLogCreate, AuthLogResponse

logger = logging.getLogger(__name__)

class AuditService:
    """Service for authentication audit logging"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_auth_event(
        self,
        user_id: Optional[int] = None,
        telegram_id: Optional[str] = None,
        event_type: str = "unknown",
        event_status: str = "unknown",
        event_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Log authentication event"""
        try:
            auth_log = AuthLog(
                user_id=user_id,
                telegram_id=telegram_id,
                event_type=event_type,
                event_status=event_status,
                event_message=event_message,
                ip_address=ip_address,
                user_agent=user_agent,
                session_id=session_id,
                auth_metadata=metadata or {},
                created_at=datetime.now(timezone.utc)
            )

            self.db.add(auth_log)
            await self.db.commit()
            await self.db.refresh(auth_log)

            logger.info(f"Logged auth event: {event_type} - {event_status} for user {user_id or telegram_id}")
            return True

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error logging auth event: {e}")
            return False

    async def get_auth_logs(
        self,
        user_id: Optional[int] = None,
        telegram_id: Optional[str] = None,
        event_type: Optional[str] = None,
        event_status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[AuthLogResponse]:
        """Get authentication logs with filters"""
        try:
            query = select(AuthLog)

            # Apply filters
            if user_id:
                query = query.where(AuthLog.user_id == user_id)
            if telegram_id:
                query = query.where(AuthLog.telegram_id == telegram_id)
            if event_type:
                query = query.where(AuthLog.event_type == event_type)
            if event_status:
                query = query.where(AuthLog.event_status == event_status)

            # Order by most recent first
            query = query.order_by(AuthLog.created_at.desc())

            # Apply pagination
            query = query.offset(offset).limit(limit)

            result = await self.db.execute(query)
            logs = result.scalars().all()

            return [AuthLogResponse.model_validate(log) for log in logs]

        except Exception as e:
            logger.error(f"Error getting auth logs: {e}")
            return []

    async def get_auth_stats(
        self,
        user_id: Optional[int] = None,
        telegram_id: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get authentication statistics"""
        try:
            # Calculate date range
            start_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            start_date = start_date - timedelta(days=days)

            query = select(
                AuthLog.event_type,
                AuthLog.event_status,
                func.count(AuthLog.id).label('count')
            ).where(AuthLog.created_at >= start_date)

            if user_id:
                query = query.where(AuthLog.user_id == user_id)
            if telegram_id:
                query = query.where(AuthLog.telegram_id == telegram_id)

            query = query.group_by(AuthLog.event_type, AuthLog.event_status)

            result = await self.db.execute(query)
            stats_raw = result.all()

            # Process statistics
            stats = {
                "total_events": 0,
                "by_event_type": {},
                "by_status": {},
                "period_days": days
            }

            for row in stats_raw:
                event_type, event_status, count = row.event_type, row.event_status, row.count

                stats["total_events"] += count

                # By event type
                if event_type not in stats["by_event_type"]:
                    stats["by_event_type"][event_type] = {"total": 0, "success": 0, "failure": 0, "error": 0}

                stats["by_event_type"][event_type]["total"] += count
                if event_status in ["success", "failure", "error"]:
                    stats["by_event_type"][event_type][event_status] += count

                # By status
                if event_status not in stats["by_status"]:
                    stats["by_status"][event_status] = 0
                stats["by_status"][event_status] += count

            return stats

        except Exception as e:
            logger.error(f"Error getting auth stats: {e}")
            return {"total_events": 0, "by_event_type": {}, "by_status": {}, "period_days": days}

    async def get_failed_login_attempts(
        self,
        telegram_id: str,
        minutes: int = 30
    ) -> int:
        """Get count of failed login attempts for user in given time period"""
        try:
            start_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)

            result = await self.db.execute(
                select(func.count(AuthLog.id))
                .where(AuthLog.telegram_id == telegram_id)
                .where(AuthLog.event_type == "login")
                .where(AuthLog.event_status == "failure")
                .where(AuthLog.created_at >= start_time)
            )

            return result.scalar() or 0

        except Exception as e:
            logger.error(f"Error getting failed login attempts: {e}")
            return 0

    async def get_recent_activity(
        self,
        user_id: int,
        limit: int = 10
    ) -> List[AuthLogResponse]:
        """Get recent authentication activity for user"""
        try:
            result = await self.db.execute(
                select(AuthLog)
                .where(AuthLog.user_id == user_id)
                .where(AuthLog.event_type.in_(["login", "logout", "token_refresh"]))
                .order_by(AuthLog.created_at.desc())
                .limit(limit)
            )

            logs = result.scalars().all()
            return [AuthLogResponse.model_validate(log) for log in logs]

        except Exception as e:
            logger.error(f"Error getting recent activity: {e}")
            return []

    async def cleanup_old_logs(self, days: int = 90) -> int:
        """Clean up old audit logs"""
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

            result = await self.db.execute(
                delete(AuthLog).where(AuthLog.created_at < cutoff_date)
            )

            await self.db.commit()
            count = result.rowcount

            logger.info(f"Cleaned up {count} old audit logs older than {days} days")
            return count

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error cleaning up old logs: {e}")
            return 0

    async def get_security_events(
        self,
        limit: int = 50
    ) -> List[AuthLogResponse]:
        """Get recent security events (failures, errors)"""
        try:
            result = await self.db.execute(
                select(AuthLog)
                .where(AuthLog.event_status.in_(["failure", "error"]))
                .order_by(AuthLog.created_at.desc())
                .limit(limit)
            )

            logs = result.scalars().all()
            return [AuthLogResponse.model_validate(log) for log in logs]

        except Exception as e:
            logger.error(f"Error getting security events: {e}")
            return []