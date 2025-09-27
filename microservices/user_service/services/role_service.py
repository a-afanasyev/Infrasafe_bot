# Role Service - User Role Management & Auth Service Integration
# UK Management Bot - User Service

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select, update, delete, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from models.user import User, UserRoleMapping
from models.access import AccessRights
from schemas.user import UserRoleMappingCreate, UserRoleMappingResponse

logger = logging.getLogger(__name__)

class RoleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_roles(self, user_id: int, active_only: bool = True) -> List[UserRoleMappingResponse]:
        """Get user roles"""
        query = select(UserRoleMapping).where(UserRoleMapping.user_id == user_id)

        if active_only:
            query = query.where(UserRoleMapping.is_active == True)

        query = query.order_by(UserRoleMapping.assigned_at.desc())

        result = await self.db.execute(query)
        roles = result.scalars().all()

        return [UserRoleMappingResponse(
            id=role.id,
            user_id=role.user_id,
            role_key=role.role_key,
            assigned_by=role.assigned_by,
            assigned_at=role.assigned_at,
            expires_at=role.expires_at,
            is_active=role.is_active,
            is_primary=role.is_primary
        ) for role in roles]

    async def assign_role(self, user_id: int, role_data: UserRoleMappingCreate) -> UserRoleMappingResponse:
        """Assign role to user"""
        # Check if user exists
        user_query = select(User).where(User.id == user_id)
        user_result = await self.db.execute(user_query)
        user = user_result.scalar_one_or_none()

        if not user:
            raise ValueError(f"User with ID {user_id} not found")

        # Validate role with Auth Service
        role_valid = await self._validate_role_with_auth_service(role_data.role_key)
        if not role_valid:
            raise ValueError(f"Invalid role: {role_data.role_key}")

        # Check if user already has this role
        existing_query = select(UserRoleMapping).where(
            and_(
                UserRoleMapping.user_id == user_id,
                UserRoleMapping.role_key == role_data.role_key,
                UserRoleMapping.is_active == True
            )
        )
        existing_result = await self.db.execute(existing_query)
        existing_role = existing_result.scalar_one_or_none()

        if existing_role:
            raise ValueError(f"User {user_id} already has active role {role_data.role_key}")

        # If this is a primary role, deactivate other primary roles
        if role_data.is_primary:
            await self._deactivate_primary_roles(user_id)

        # Create role mapping
        role_mapping = UserRoleMapping(
            user_id=user_id,
            role_key=role_data.role_key,
            assigned_by=role_data.assigned_by,
            expires_at=role_data.expires_at,
            is_primary=role_data.is_primary,
            is_active=True
        )

        self.db.add(role_mapping)
        await self.db.commit()
        await self.db.refresh(role_mapping)

        # Update user permissions based on new role
        await self._update_user_permissions(user_id)

        # Sync with Auth Service
        await self._sync_role_with_auth_service(user_id, role_data.role_key, "assign")

        logger.info(f"Assigned role {role_data.role_key} to user {user_id}")

        return UserRoleMappingResponse(
            id=role_mapping.id,
            user_id=role_mapping.user_id,
            role_key=role_mapping.role_key,
            assigned_by=role_mapping.assigned_by,
            assigned_at=role_mapping.assigned_at,
            expires_at=role_mapping.expires_at,
            is_active=role_mapping.is_active,
            is_primary=role_mapping.is_primary
        )

    async def update_role(self, user_id: int, role_id: int, update_data: Dict[str, Any]) -> Optional[UserRoleMappingResponse]:
        """Update user role"""
        # Check if role belongs to user
        role_query = select(UserRoleMapping).where(
            and_(
                UserRoleMapping.id == role_id,
                UserRoleMapping.user_id == user_id
            )
        )
        role_result = await self.db.execute(role_query)
        role = role_result.scalar_one_or_none()

        if not role:
            return None

        # If setting as primary, deactivate other primary roles
        if update_data.get("is_primary", False):
            await self._deactivate_primary_roles(user_id, exclude_role_id=role_id)

        # Update role
        query = update(UserRoleMapping).where(UserRoleMapping.id == role_id).values(**update_data)
        await self.db.execute(query)
        await self.db.commit()

        # Update user permissions
        await self._update_user_permissions(user_id)

        # Sync with Auth Service if status changed
        if "is_active" in update_data:
            action = "assign" if update_data["is_active"] else "remove"
            await self._sync_role_with_auth_service(user_id, role.role_key, action)

        logger.info(f"Updated role {role_id} for user {user_id} with data: {update_data}")

        # Get updated role
        updated_query = select(UserRoleMapping).where(UserRoleMapping.id == role_id)
        updated_result = await self.db.execute(updated_query)
        updated_role = updated_result.scalar_one()

        return UserRoleMappingResponse(
            id=updated_role.id,
            user_id=updated_role.user_id,
            role_key=updated_role.role_key,
            assigned_by=updated_role.assigned_by,
            assigned_at=updated_role.assigned_at,
            expires_at=updated_role.expires_at,
            is_active=updated_role.is_active,
            is_primary=updated_role.is_primary
        )

    async def remove_role(self, user_id: int, role_id: int) -> bool:
        """Remove role from user"""
        # Check if role belongs to user
        role_query = select(UserRoleMapping).where(
            and_(
                UserRoleMapping.id == role_id,
                UserRoleMapping.user_id == user_id
            )
        )
        role_result = await self.db.execute(role_query)
        role = role_result.scalar_one_or_none()

        if not role:
            return False

        # Deactivate role instead of deleting (for audit purposes)
        query = update(UserRoleMapping).where(UserRoleMapping.id == role_id).values(
            is_active=False
        )
        await self.db.execute(query)
        await self.db.commit()

        # Update user permissions
        await self._update_user_permissions(user_id)

        # Sync with Auth Service
        await self._sync_role_with_auth_service(user_id, role.role_key, "remove")

        logger.info(f"Removed role {role_id} from user {user_id}")

        return True

    async def set_active_role(self, user_id: int, role_key: str) -> bool:
        """Set user's active (primary) role"""
        # Check if user has this role
        role_query = select(UserRoleMapping).where(
            and_(
                UserRoleMapping.user_id == user_id,
                UserRoleMapping.role_key == role_key,
                UserRoleMapping.is_active == True
            )
        )
        role_result = await self.db.execute(role_query)
        role = role_result.scalar_one_or_none()

        if not role:
            raise ValueError(f"User {user_id} does not have active role {role_key}")

        # Deactivate other primary roles
        await self._deactivate_primary_roles(user_id)

        # Set this role as primary
        query = update(UserRoleMapping).where(UserRoleMapping.id == role.id).values(
            is_primary=True
        )
        await self.db.execute(query)
        await self.db.commit()

        # Update user permissions
        await self._update_user_permissions(user_id)

        # Sync with Auth Service
        await self._sync_primary_role_with_auth_service(user_id, role_key)

        logger.info(f"Set active role {role_key} for user {user_id}")

        return True

    async def get_active_role(self, user_id: int) -> Optional[str]:
        """Get user's active (primary) role"""
        query = select(UserRoleMapping.role_key).where(
            and_(
                UserRoleMapping.user_id == user_id,
                UserRoleMapping.is_active == True,
                UserRoleMapping.is_primary == True
            )
        )
        result = await self.db.execute(query)
        role_key = result.scalar_one_or_none()

        return role_key

    async def get_users_by_role(self, role_key: str, active_only: bool = True, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all users with specific role"""
        query = select(User, UserRoleMapping).join(UserRoleMapping).where(
            UserRoleMapping.role_key == role_key
        )

        if active_only:
            query = query.where(
                and_(
                    UserRoleMapping.is_active == True,
                    User.is_active == True
                )
            )

        query = query.limit(limit).order_by(User.first_name, User.last_name)

        result = await self.db.execute(query)
        user_roles = result.fetchall()

        users_data = []
        for user, role_mapping in user_roles:
            users_data.append({
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "status": user.status,
                "is_active": user.is_active,
                "role_assigned_at": role_mapping.assigned_at,
                "role_expires_at": role_mapping.expires_at,
                "is_primary_role": role_mapping.is_primary
            })

        return users_data

    async def get_role_distribution(self) -> Dict[str, int]:
        """Get role distribution statistics"""
        query = select(UserRoleMapping.role_key, func.count(UserRoleMapping.user_id)).where(
            UserRoleMapping.is_active == True
        ).group_by(UserRoleMapping.role_key)

        result = await self.db.execute(query)
        distribution = dict(result.fetchall())

        return distribution

    async def sync_with_auth_service(self, user_id: int) -> bool:
        """Synchronize user roles with Auth Service"""
        try:
            # Get user's active roles
            user_roles = await self.get_user_roles(user_id, active_only=True)
            role_keys = [role.role_key for role in user_roles]

            # Get user's telegram_id
            user_query = select(User.telegram_id).where(User.id == user_id)
            user_result = await self.db.execute(user_query)
            telegram_id = user_result.scalar_one_or_none()

            if not telegram_id:
                raise ValueError(f"User {user_id} not found")

            # Sync with Auth Service
            async with httpx.AsyncClient() as client:
                sync_data = {
                    "user_id": user_id,
                    "telegram_id": telegram_id,
                    "roles": role_keys
                }

                response = await client.post(
                    "http://auth-service:8000/api/v1/auth/sync-user-roles",
                    json=sync_data,
                    timeout=10.0
                )

                if response.status_code != 200:
                    logger.error(f"Failed to sync roles with Auth Service: {response.text}")
                    return False

                logger.info(f"Successfully synced roles for user {user_id} with Auth Service")
                return True

        except httpx.RequestError as e:
            logger.error(f"Failed to connect to Auth Service for user {user_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Role sync error for user {user_id}: {e}")
            return False

    async def _validate_role_with_auth_service(self, role_key: str) -> bool:
        """Validate role exists in Auth Service"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://auth-service:8000/api/v1/permissions/roles/{role_key}",
                    timeout=5.0
                )

                return response.status_code == 200

        except Exception as e:
            logger.warning(f"Failed to validate role {role_key} with Auth Service: {e}")
            # Allow role assignment even if Auth Service is unavailable
            return True

    async def _sync_role_with_auth_service(self, user_id: int, role_key: str, action: str):
        """Sync specific role action with Auth Service"""
        try:
            # Get user's telegram_id
            user_query = select(User.telegram_id).where(User.id == user_id)
            user_result = await self.db.execute(user_query)
            telegram_id = user_result.scalar_one_or_none()

            if not telegram_id:
                return

            async with httpx.AsyncClient() as client:
                sync_data = {
                    "user_id": user_id,
                    "telegram_id": telegram_id,
                    "role_key": role_key,
                    "action": action  # "assign" or "remove"
                }

                response = await client.post(
                    "http://auth-service:8000/api/v1/auth/sync-user-role-action",
                    json=sync_data,
                    timeout=5.0
                )

                if response.status_code != 200:
                    logger.warning(f"Failed to sync role action with Auth Service: {response.text}")

        except Exception as e:
            logger.warning(f"Failed to sync role action for user {user_id}: {e}")

    async def _sync_primary_role_with_auth_service(self, user_id: int, role_key: str):
        """Sync primary role with Auth Service"""
        try:
            # Get user's telegram_id
            user_query = select(User.telegram_id).where(User.id == user_id)
            user_result = await self.db.execute(user_query)
            telegram_id = user_result.scalar_one_or_none()

            if not telegram_id:
                return

            async with httpx.AsyncClient() as client:
                sync_data = {
                    "user_id": user_id,
                    "telegram_id": telegram_id,
                    "primary_role": role_key
                }

                response = await client.post(
                    "http://auth-service:8000/api/v1/auth/sync-primary-role",
                    json=sync_data,
                    timeout=5.0
                )

                if response.status_code != 200:
                    logger.warning(f"Failed to sync primary role with Auth Service: {response.text}")

        except Exception as e:
            logger.warning(f"Failed to sync primary role for user {user_id}: {e}")

    async def _deactivate_primary_roles(self, user_id: int, exclude_role_id: Optional[int] = None):
        """Deactivate all primary roles for user"""
        query = update(UserRoleMapping).where(
            and_(
                UserRoleMapping.user_id == user_id,
                UserRoleMapping.is_primary == True
            )
        ).values(is_primary=False)

        if exclude_role_id:
            query = query.where(UserRoleMapping.id != exclude_role_id)

        await self.db.execute(query)

    async def _update_user_permissions(self, user_id: int):
        """Update user permissions based on roles"""
        try:
            # Get user's active roles
            roles_query = select(UserRoleMapping.role_key).where(
                and_(
                    UserRoleMapping.user_id == user_id,
                    UserRoleMapping.is_active == True
                )
            )
            roles_result = await self.db.execute(roles_query)
            role_keys = [row[0] for row in roles_result.fetchall()]

            # Define role permissions
            role_permissions = {
                "applicant": {
                    "can_create_requests": True,
                    "can_view_all_requests": False,
                    "can_manage_users": False,
                    "can_access_analytics": False,
                    "can_manage_shifts": False,
                    "can_export_data": False
                },
                "executor": {
                    "can_create_requests": True,
                    "can_view_all_requests": True,
                    "can_manage_users": False,
                    "can_access_analytics": False,
                    "can_manage_shifts": False,
                    "can_export_data": False
                },
                "manager": {
                    "can_create_requests": True,
                    "can_view_all_requests": True,
                    "can_manage_users": True,
                    "can_access_analytics": True,
                    "can_manage_shifts": True,
                    "can_export_data": True
                },
                "admin": {
                    "can_create_requests": True,
                    "can_view_all_requests": True,
                    "can_manage_users": True,
                    "can_access_analytics": True,
                    "can_manage_shifts": True,
                    "can_export_data": True
                }
            }

            # Calculate combined permissions (OR logic)
            combined_permissions = {
                "can_create_requests": False,
                "can_view_all_requests": False,
                "can_manage_users": False,
                "can_access_analytics": False,
                "can_manage_shifts": False,
                "can_export_data": False
            }

            for role_key in role_keys:
                if role_key in role_permissions:
                    role_perms = role_permissions[role_key]
                    for perm, value in role_perms.items():
                        if value:
                            combined_permissions[perm] = True

            # Update access rights
            query = update(AccessRights).where(AccessRights.user_id == user_id).values(**combined_permissions)
            result = await self.db.execute(query)

            # If no access rights record exists, create one
            if result.rowcount == 0:
                access_rights = AccessRights(user_id=user_id, **combined_permissions)
                self.db.add(access_rights)

            await self.db.commit()

            logger.info(f"Updated permissions for user {user_id} based on roles: {role_keys}")

        except Exception as e:
            logger.error(f"Failed to update permissions for user {user_id}: {e}")

    async def check_role_expiration(self):
        """Check and deactivate expired roles (called by scheduler)"""
        try:
            # Find expired roles
            expired_query = select(UserRoleMapping).where(
                and_(
                    UserRoleMapping.is_active == True,
                    UserRoleMapping.expires_at <= datetime.utcnow()
                )
            )
            expired_result = await self.db.execute(expired_query)
            expired_roles = expired_result.scalars().all()

            for role in expired_roles:
                # Deactivate role
                query = update(UserRoleMapping).where(UserRoleMapping.id == role.id).values(
                    is_active=False
                )
                await self.db.execute(query)

                # Update user permissions
                await self._update_user_permissions(role.user_id)

                # Sync with Auth Service
                await self._sync_role_with_auth_service(role.user_id, role.role_key, "remove")

                logger.info(f"Deactivated expired role {role.role_key} for user {role.user_id}")

            await self.db.commit()

            if expired_roles:
                logger.info(f"Processed {len(expired_roles)} expired roles")

        except Exception as e:
            logger.error(f"Failed to check role expiration: {e}")