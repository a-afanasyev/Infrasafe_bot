# User Service - Core User Management
# UK Management Bot - User Service

import logging
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy import select, and_, or_, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import httpx

from models.user import User
from models.access import AccessRights
from schemas.user import UserCreate, UserResponse, UserFullResponse, UserSearchFilters, UserStatsResponse, ExecutorResponse

logger = logging.getLogger(__name__)

class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_user(self, user_data: UserCreate) -> UserFullResponse:
        """Create new user"""
        # Check if user with telegram_id already exists
        existing_user = await self.get_user_by_telegram_id(user_data.telegram_id)
        if existing_user:
            raise ValueError(f"User with telegram_id {user_data.telegram_id} already exists")

        # Check if username is taken (if provided)
        if user_data.username:
            existing_username = await self.db.execute(
                select(User).where(User.username == user_data.username)
            )
            if existing_username.scalar_one_or_none():
                raise ValueError(f"Username {user_data.username} is already taken")

        # Create user
        user = User(
            telegram_id=user_data.telegram_id,
            username=user_data.username,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            phone=user_data.phone,
            email=user_data.email,
            language_code=user_data.language_code or "ru",
            status="pending",
            is_active=True
        )

        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)

        # Create initial access rights
        access_rights = AccessRights(
            user_id=user.id,
            access_level="basic",
            service_permissions={
                "can_create_requests": False,  # Will be granted after verification
                "can_view_all_requests": False,
                "can_manage_users": False,
                "can_access_analytics": False,
                "can_manage_shifts": False,
                "can_export_data": False
            },
            is_active=True
        )

        self.db.add(access_rights)
        await self.db.commit()

        logger.info(f"Created user {user.id} with telegram_id {user.telegram_id}")

        return await self._build_user_full_response(user)

    async def get_user_by_id(self, user_id: int) -> Optional[UserFullResponse]:
        """Get user by ID"""
        query = select(User).options(
            selectinload(User.profile),
            selectinload(User.roles),
            selectinload(User.verifications),
            selectinload(User.access_rights)
        ).where(User.id == user_id)

        result = await self.db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            return None

        return await self._build_user_full_response(user)

    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[UserFullResponse]:
        """Get user by Telegram ID"""
        query = select(User).options(
            selectinload(User.profile),
            selectinload(User.roles),
            selectinload(User.verifications),
            selectinload(User.access_rights)
        ).where(User.telegram_id == telegram_id)

        result = await self.db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            return None

        return await self._build_user_full_response(user)

    async def update_user(self, user_id: int, update_data: Dict[str, Any]) -> Optional[UserFullResponse]:
        """Update user information"""
        # Check if username is being changed and if it's taken
        if "username" in update_data and update_data["username"]:
            existing_username = await self.db.execute(
                select(User).where(
                    and_(
                        User.username == update_data["username"],
                        User.id != user_id
                    )
                )
            )
            if existing_username.scalar_one_or_none():
                raise ValueError(f"Username {update_data['username']} is already taken")

        # Update user
        query = update(User).where(User.id == user_id).values(**update_data)
        result = await self.db.execute(query)

        if result.rowcount == 0:
            return None

        await self.db.commit()

        logger.info(f"Updated user {user_id} with data: {update_data}")

        return await self.get_user_by_id(user_id)

    async def archive_user(self, user_id: int) -> bool:
        """Archive user (soft delete)"""
        query = update(User).where(User.id == user_id).values(
            status="archived",
            is_active=False
        )

        result = await self.db.execute(query)

        if result.rowcount == 0:
            return False

        await self.db.commit()

        logger.info(f"Archived user {user_id}")

        return True

    async def change_user_status(self, user_id: int, status: str) -> Optional[UserFullResponse]:
        """Change user status"""
        valid_statuses = ["pending", "approved", "blocked", "archived"]
        if status not in valid_statuses:
            raise ValueError(f"Invalid status. Must be one of: {valid_statuses}")

        # Update status and activity
        is_active = status not in ["blocked", "archived"]

        query = update(User).where(User.id == user_id).values(
            status=status,
            is_active=is_active
        )

        result = await self.db.execute(query)

        if result.rowcount == 0:
            return None

        await self.db.commit()

        logger.info(f"Changed user {user_id} status to {status}")

        return await self.get_user_by_id(user_id)

    async def activate_user(self, user_id: int) -> Optional[UserFullResponse]:
        """Activate user account"""
        return await self.change_user_status(user_id, "approved")

    async def deactivate_user(self, user_id: int) -> Optional[UserFullResponse]:
        """Deactivate user account"""
        return await self.change_user_status(user_id, "blocked")

    async def get_users_list(
        self,
        filters: UserSearchFilters,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[UserResponse], int]:
        """Get paginated list of users with filters"""
        # Base query
        query = select(User)

        # Apply filters
        conditions = []

        if filters.status:
            conditions.append(User.status == filters.status)

        if filters.role_key:
            # Join with roles to filter by role
            from models.user import UserRoleMapping
            query = query.join(UserRoleMapping).where(UserRoleMapping.role_key == filters.role_key)

        # Apply search
        if search:
            search_conditions = [
                User.first_name.ilike(f"%{search}%"),
                User.last_name.ilike(f"%{search}%"),
                User.username.ilike(f"%{search}%")
            ]
            conditions.append(or_(*search_conditions))

        if conditions:
            query = query.where(and_(*conditions))

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_count = await self.db.execute(count_query)
        total_count = total_count.scalar()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(User.created_at.desc())

        result = await self.db.execute(query)
        users = result.scalars().all()

        # Convert to response objects
        user_responses = []
        for user in users:
            user_responses.append(UserResponse(
                id=user.id,
                telegram_id=user.telegram_id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                phone=user.phone,
                email=user.email,
                language_code=user.language_code,
                status=user.status,
                is_active=user.is_active,
                created_at=user.created_at,
                updated_at=user.updated_at
            ))

        return user_responses, total_count

    async def get_executors_list(
        self,
        specialization: Optional[str] = None,
        status: Optional[str] = None,
        availability_status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get paginated list of executors with executor-specific information"""
        from models.user import UserRoleMapping, UserProfile

        # Base query - join with roles to get only executors
        query = select(User).join(UserRoleMapping).where(
            UserRoleMapping.role_key == "executor",
            UserRoleMapping.is_active == True
        ).options(
            selectinload(User.roles),
            selectinload(User.profile)
        )

        # Apply filters
        conditions = []

        if status:
            conditions.append(User.status == status)
        else:
            # Default to active executors only
            conditions.append(User.status == "approved")
            conditions.append(User.is_active == True)

        if availability_status == "available":
            # Add availability logic here if needed
            pass

        if specialization:
            # Filter by specialization in profile
            query = query.join(UserProfile).where(
                UserProfile.specialization.contains([specialization])
            )

        if conditions:
            query = query.where(and_(*conditions))

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_count = await self.db.execute(count_query)
        total_count = total_count.scalar()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(User.created_at.desc())

        result = await self.db.execute(query)
        users = result.scalars().all()

        # Convert to executor response objects
        executor_responses = []
        for user in users:
            # Get specializations from profile
            specializations = []
            if user.profile and user.profile.specialization:
                specializations = user.profile.specialization

            # Calculate executor-specific metrics
            current_workload = await self._calculate_executor_workload(user.id)
            availability_score = await self._calculate_availability_score(user.id)
            rating = await self._calculate_executor_rating(user.id)

            # Get executor-specific configuration from profile
            max_concurrent_requests = 5  # Default value
            executor_config = None
            if user.profile:
                max_concurrent_requests = getattr(user.profile, 'max_concurrent_requests', 5) or 5
                executor_config = getattr(user.profile, 'executor_config', None)

            executor_data = {
                "id": user.id,
                "telegram_id": user.telegram_id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "phone": user.phone,
                "email": user.email,
                "language_code": user.language_code,
                "status": user.status,
                "is_active": user.is_active,
                "created_at": user.created_at,
                "updated_at": user.updated_at,
                "profile": user.profile,
                "roles": user.roles,
                "current_workload": current_workload,
                "specializations": specializations,
                "availability_score": availability_score,
                "rating": rating,
                "max_concurrent_requests": max_concurrent_requests,
                "executor_config": executor_config
            }
            executor_responses.append(executor_data)

        return executor_responses, total_count

    async def _calculate_executor_workload(self, user_id: int) -> int:
        """Calculate current workload for executor (placeholder implementation)"""
        # This would integrate with Request Service to get actual workload
        # For now, return a mock value
        return 0

    async def _calculate_availability_score(self, user_id: int) -> float:
        """Calculate availability score for executor (placeholder implementation)"""
        # This would calculate based on schedule, current assignments, etc.
        # For now, return a default value
        return 1.0

    async def _calculate_executor_rating(self, user_id: int) -> Optional[float]:
        """Calculate average rating for executor (placeholder implementation)"""
        # This would integrate with rating/review system
        # For now, return None
        return None

    async def search_users_by_username(self, username: str, limit: int = 10) -> List[UserResponse]:
        """Search users by username"""
        query = select(User).where(
            User.username.ilike(f"%{username}%")
        ).limit(limit).order_by(User.username)

        result = await self.db.execute(query)
        users = result.scalars().all()

        return [UserResponse(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            phone=user.phone,
            email=user.email,
            language_code=user.language_code,
            status=user.status,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at
        ) for user in users]

    async def get_user_stats(self) -> UserStatsResponse:
        """Get user statistics"""
        # Total users count
        total_query = select(func.count(User.id))
        total_users = await self.db.execute(total_query)
        total_users = total_users.scalar()

        # Active users count
        active_query = select(func.count(User.id)).where(User.is_active == True)
        active_users = await self.db.execute(active_query)
        active_users = active_users.scalar()

        # Users by status
        status_query = select(User.status, func.count(User.id)).group_by(User.status)
        status_result = await self.db.execute(status_query)
        status_distribution = dict(status_result.fetchall())

        # Users by role (if roles exist)
        from models.user import UserRoleMapping
        role_query = select(UserRoleMapping.role_key, func.count(UserRoleMapping.user_id)).group_by(UserRoleMapping.role_key)
        role_result = await self.db.execute(role_query)
        role_distribution = dict(role_result.fetchall())

        # Users registered this month
        from datetime import datetime, timedelta
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_query = select(func.count(User.id)).where(User.created_at >= month_start)
        monthly_users = await self.db.execute(monthly_query)
        monthly_users = monthly_users.scalar()

        return UserStatsResponse(
            total_users=total_users,
            active_users=active_users,
            status_distribution=status_distribution,
            role_distribution=role_distribution,
            monthly_registrations=monthly_users
        )

    async def _build_user_full_response(self, user: User) -> UserFullResponse:
        """Build full user response with all related data"""
        # Get profile (uselist=False means single object, not list)
        profile = user.profile if user.profile else None

        # Get roles - need to build UserRoleMappingResponse objects
        from schemas.user import UserRoleMappingResponse
        roles = []
        if user.roles:
            for role in user.roles:
                roles.append(UserRoleMappingResponse(
                    id=role.id,
                    user_id=role.user_id,  # Required field that was missing
                    role_key=role.role_key,
                    role_data=role.role_data,
                    is_active_role=role.is_active_role,
                    assigned_at=role.assigned_at,
                    assigned_by=role.assigned_by,
                    expires_at=role.expires_at,
                    is_active=role.is_active
                ))

        # Get verification status
        verification_status = "not_started"
        if user.verifications:
            latest_verification = max(user.verifications, key=lambda v: v.created_at)
            verification_status = latest_verification.status

        # Get access rights (uselist=False means single object, not list)
        # Convert SQLAlchemy entity to dict for serialization
        access_rights = None
        if user.access_rights:
            access_rights = {
                "id": user.access_rights.id,
                "access_level": user.access_rights.access_level,
                "access_scope": user.access_rights.access_scope,
                "building_access": user.access_rights.building_access,
                "area_access": user.access_rights.area_access,
                "service_permissions": user.access_rights.service_permissions,
                "feature_flags": user.access_rights.feature_flags,
                "restrictions": user.access_rights.restrictions,
                "daily_limits": user.access_rights.daily_limits,
                "is_active": user.access_rights.is_active,
                "is_temporary": user.access_rights.is_temporary,
                "granted_at": user.access_rights.granted_at.isoformat() if user.access_rights.granted_at else None,
                "granted_by": user.access_rights.granted_by,
                "expires_at": user.access_rights.expires_at.isoformat() if user.access_rights.expires_at else None,
                "last_used_at": user.access_rights.last_used_at.isoformat() if user.access_rights.last_used_at else None
            }

        return UserFullResponse(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            phone=user.phone,
            email=user.email,
            language_code=user.language_code,
            status=user.status,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
            profile=profile,
            roles=roles,
            verification_status=verification_status,
            access_rights=access_rights
        )


# Create global instance for dependency injection
def get_user_service(db: AsyncSession) -> UserService:
    """Dependency to get UserService instance"""
    return UserService(db)

# For backward compatibility with existing imports
user_service = None  # Will be initialized with DB session when needed