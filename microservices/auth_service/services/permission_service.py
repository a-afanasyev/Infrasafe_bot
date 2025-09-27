# Permission Management Service
# UK Management Bot - Auth Service

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.orm import selectinload

from models.auth import Permission, UserRole
from schemas.auth import (
    PermissionCreate, PermissionResponse, PermissionUpdate,
    UserRoleCreate, UserRoleResponse, UserRoleUpdate,
    PermissionCheckResponse
)
from config import settings

logger = logging.getLogger(__name__)

class PermissionService:
    """Service for managing permissions and user roles"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # Permission CRUD operations
    async def create_permission(self, permission_data: PermissionCreate) -> PermissionResponse:
        """Create new permission"""
        try:
            # Check if permission already exists
            existing = await self.db.execute(
                select(Permission).where(Permission.permission_key == permission_data.permission_key)
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Permission '{permission_data.permission_key}' already exists")

            permission = Permission(
                permission_key=permission_data.permission_key,
                permission_name=permission_data.permission_name,
                description=permission_data.description,
                service_name=permission_data.service_name,
                resource_type=permission_data.resource_type,
                is_active=permission_data.is_active,
                is_system=permission_data.is_system
            )

            self.db.add(permission)
            await self.db.commit()
            await self.db.refresh(permission)

            logger.info(f"Created permission: {permission_data.permission_key}")
            return PermissionResponse.model_validate(permission)

        except ValueError:
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating permission: {e}")
            raise Exception("Could not create permission")

    async def get_permission(self, permission_id: int) -> Optional[PermissionResponse]:
        """Get permission by ID"""
        try:
            result = await self.db.execute(
                select(Permission).where(Permission.id == permission_id)
            )
            permission = result.scalar_one_or_none()

            if permission:
                return PermissionResponse.model_validate(permission)
            return None

        except Exception as e:
            logger.error(f"Error getting permission {permission_id}: {e}")
            return None

    async def get_permissions(
        self,
        service_name: Optional[str] = None,
        active_only: bool = True
    ) -> List[PermissionResponse]:
        """Get all permissions with optional filters"""
        try:
            query = select(Permission)

            if service_name:
                query = query.where(Permission.service_name == service_name)
            if active_only:
                query = query.where(Permission.is_active == True)

            query = query.order_by(Permission.service_name, Permission.permission_key)

            result = await self.db.execute(query)
            permissions = result.scalars().all()

            return [PermissionResponse.model_validate(p) for p in permissions]

        except Exception as e:
            logger.error(f"Error getting permissions: {e}")
            return []

    async def update_permission(
        self,
        permission_id: int,
        update_data: Dict[str, Any]
    ) -> Optional[PermissionResponse]:
        """Update permission"""
        try:
            update_data["updated_at"] = datetime.now(timezone.utc)

            result = await self.db.execute(
                update(Permission)
                .where(Permission.id == permission_id)
                .values(**update_data)
            )

            await self.db.commit()

            if result.rowcount > 0:
                return await self.get_permission(permission_id)
            return None

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating permission {permission_id}: {e}")
            return None

    # User Role Management
    async def get_user_roles(self, user_id: int, active_only: bool = True) -> List[UserRoleResponse]:
        """Get all roles for a user"""
        try:
            query = select(UserRole).where(UserRole.user_id == user_id)

            if active_only:
                query = query.where(UserRole.is_active == True)
                query = query.where(
                    or_(
                        UserRole.expires_at.is_(None),
                        UserRole.expires_at > datetime.now(timezone.utc)
                    )
                )

            query = query.order_by(UserRole.assigned_at.desc())

            result = await self.db.execute(query)
            roles = result.scalars().all()

            return [UserRoleResponse.model_validate(role) for role in roles]

        except Exception as e:
            logger.error(f"Error getting user roles for user {user_id}: {e}")
            return []

    async def assign_user_role(self, user_id: int, role_data: Dict[str, Any]) -> UserRoleResponse:
        """Assign role to user"""
        try:
            # Check if user already has this role
            existing = await self.db.execute(
                select(UserRole)
                .where(UserRole.user_id == user_id)
                .where(UserRole.role_key == role_data["role_key"])
                .where(UserRole.is_active == True)
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"User already has role '{role_data['role_key']}'")

            # If this is being set as active role, deactivate other active roles
            if role_data.get("is_active_role", False):
                await self.db.execute(
                    update(UserRole)
                    .where(UserRole.user_id == user_id)
                    .where(UserRole.is_active_role == True)
                    .values(is_active_role=False)
                )

            user_role = UserRole(
                user_id=user_id,
                telegram_id=role_data["telegram_id"],
                role_key=role_data["role_key"],
                role_name=role_data["role_name"],
                is_active_role=role_data.get("is_active_role", False),
                role_data=role_data.get("role_data"),
                additional_permissions=role_data.get("additional_permissions"),
                denied_permissions=role_data.get("denied_permissions"),
                assigned_by=role_data.get("assigned_by"),
                expires_at=role_data.get("expires_at"),
                is_active=True
            )

            self.db.add(user_role)
            await self.db.commit()
            await self.db.refresh(user_role)

            logger.info(f"Assigned role {role_data['role_key']} to user {user_id}")
            return UserRoleResponse.model_validate(user_role)

        except ValueError:
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error assigning role to user {user_id}: {e}")
            raise Exception("Could not assign role")

    async def update_user_role(
        self,
        user_id: int,
        role_id: int,
        update_data: Dict[str, Any]
    ) -> Optional[UserRoleResponse]:
        """Update user role"""
        try:
            # If setting as active role, deactivate other active roles
            if update_data.get("is_active_role", False):
                await self.db.execute(
                    update(UserRole)
                    .where(UserRole.user_id == user_id)
                    .where(UserRole.id != role_id)
                    .where(UserRole.is_active_role == True)
                    .values(is_active_role=False)
                )

            result = await self.db.execute(
                update(UserRole)
                .where(UserRole.id == role_id)
                .where(UserRole.user_id == user_id)
                .values(**update_data)
            )

            await self.db.commit()

            if result.rowcount > 0:
                # Get updated role
                updated_role = await self.db.execute(
                    select(UserRole).where(UserRole.id == role_id)
                )
                role = updated_role.scalar_one_or_none()
                if role:
                    return UserRoleResponse.model_validate(role)

            return None

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating user role {role_id}: {e}")
            return None

    async def remove_user_role(self, user_id: int, role_id: int) -> bool:
        """Remove (deactivate) user role"""
        try:
            result = await self.db.execute(
                update(UserRole)
                .where(UserRole.id == role_id)
                .where(UserRole.user_id == user_id)
                .values(is_active=False)
            )

            await self.db.commit()
            success = result.rowcount > 0

            if success:
                logger.info(f"Removed role {role_id} from user {user_id}")

            return success

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error removing user role {role_id}: {e}")
            return False

    # Permission Checking
    async def check_user_permission(
        self,
        user_id: int,
        telegram_id: str,
        permission_key: str,
        resource_id: Optional[str] = None
    ) -> PermissionCheckResponse:
        """Check if user has specific permission"""
        try:
            # Get user's active roles
            user_roles = await self.get_user_roles(user_id, active_only=True)

            if not user_roles:
                return PermissionCheckResponse(
                    has_permission=False,
                    user_roles=[],
                    effective_permissions=[],
                    reason="No active roles found"
                )

            # Extract role keys
            role_keys = [role.role_key for role in user_roles]

            # Check if user is admin (admins have all permissions)
            if any(role in ["admin", "superadmin"] for role in role_keys):
                return PermissionCheckResponse(
                    has_permission=True,
                    user_roles=role_keys,
                    effective_permissions=["*"],
                    reason="Admin access"
                )

            # Get effective permissions for all user roles
            effective_permissions = await self.get_user_effective_permissions(user_id)

            # Check if user has the required permission
            has_permission = permission_key in effective_permissions

            return PermissionCheckResponse(
                has_permission=has_permission,
                user_roles=role_keys,
                effective_permissions=effective_permissions,
                reason="Permission granted" if has_permission else "Permission denied"
            )

        except Exception as e:
            logger.error(f"Error checking user permission: {e}")
            return PermissionCheckResponse(
                has_permission=False,
                user_roles=[],
                effective_permissions=[],
                reason="Error checking permission"
            )

    async def get_user_effective_permissions(
        self,
        user_id: int,
        service_name: Optional[str] = None
    ) -> List[str]:
        """Get effective permissions for user based on their roles"""
        try:
            # Get user's active roles
            user_roles = await self.get_user_roles(user_id, active_only=True)

            if not user_roles:
                return []

            # Collect all permissions from role-based mapping
            effective_permissions = set()

            # Basic role-permission mapping (will be expanded)
            role_permissions = {
                "admin": ["*"],  # Admin has all permissions
                "superadmin": ["*"],
                "manager": [
                    "auth:login", "auth:logout", "auth:refresh_token",
                    "users:read", "users:create", "users:update",
                    "requests:read", "requests:create", "requests:update", "requests:assign",
                    "shifts:read", "shifts:create", "shifts:update",
                    "notifications:send", "notifications:read",
                    "analytics:read"
                ],
                "executor": [
                    "auth:login", "auth:logout", "auth:refresh_token",
                    "requests:read", "requests:update_own",
                    "shifts:read_own", "notifications:read"
                ],
                "applicant": [
                    "auth:login", "auth:logout", "auth:refresh_token",
                    "requests:create", "requests:read_own",
                    "notifications:read"
                ]
            }

            # Add role-based permissions
            for role in user_roles:
                role_key = role.role_key
                if role_key in role_permissions:
                    if role_permissions[role_key] == ["*"]:
                        return ["*"]  # Admin access
                    effective_permissions.update(role_permissions[role_key])

                # Add additional permissions
                if role.additional_permissions:
                    effective_permissions.update(role.additional_permissions)

                # Remove denied permissions
                if role.denied_permissions:
                    effective_permissions -= set(role.denied_permissions)

            # Filter by service if specified
            if service_name and "*" not in effective_permissions:
                effective_permissions = {
                    perm for perm in effective_permissions
                    if perm.startswith(f"{service_name}:")
                }

            return sorted(list(effective_permissions))

        except Exception as e:
            logger.error(f"Error getting effective permissions for user {user_id}: {e}")
            return []

    async def initialize_default_permissions(self) -> int:
        """Initialize default system permissions"""
        try:
            default_permissions = [
                # Auth Service permissions
                {"key": "auth:login", "name": "Login", "service": "auth-service", "description": "User login"},
                {"key": "auth:logout", "name": "Logout", "service": "auth-service", "description": "User logout"},
                {"key": "auth:refresh_token", "name": "Refresh Token", "service": "auth-service", "description": "Refresh access token"},
                {"key": "auth:manage_sessions", "name": "Manage Sessions", "service": "auth-service", "description": "Manage user sessions"},
                {"key": "auth:manage_permissions", "name": "Manage Permissions", "service": "auth-service", "description": "Manage permissions"},

                # User Service permissions (placeholder)
                {"key": "users:read", "name": "Read Users", "service": "user-service", "description": "View user information"},
                {"key": "users:create", "name": "Create Users", "service": "user-service", "description": "Create new users"},
                {"key": "users:update", "name": "Update Users", "service": "user-service", "description": "Update user information"},
                {"key": "users:delete", "name": "Delete Users", "service": "user-service", "description": "Delete users"},

                # Request Service permissions (placeholder)
                {"key": "requests:read", "name": "Read Requests", "service": "request-service", "description": "View requests"},
                {"key": "requests:create", "name": "Create Requests", "service": "request-service", "description": "Create new requests"},
                {"key": "requests:update", "name": "Update Requests", "service": "request-service", "description": "Update requests"},
                {"key": "requests:assign", "name": "Assign Requests", "service": "request-service", "description": "Assign requests to users"},

                # Notification Service permissions
                {"key": "notifications:send", "name": "Send Notifications", "service": "notification-service", "description": "Send notifications"},
                {"key": "notifications:read", "name": "Read Notifications", "service": "notification-service", "description": "View notifications"},

                # Analytics Service permissions (placeholder)
                {"key": "analytics:read", "name": "Read Analytics", "service": "analytics-service", "description": "View analytics and reports"}
            ]

            created_count = 0

            for perm_data in default_permissions:
                # Check if permission already exists
                existing = await self.db.execute(
                    select(Permission).where(Permission.permission_key == perm_data["key"])
                )

                if not existing.scalar_one_or_none():
                    permission = Permission(
                        permission_key=perm_data["key"],
                        permission_name=perm_data["name"],
                        service_name=perm_data["service"],
                        description=perm_data["description"],
                        is_system=True,
                        is_active=True
                    )
                    self.db.add(permission)
                    created_count += 1

            await self.db.commit()
            logger.info(f"Initialized {created_count} default permissions")
            return created_count

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error initializing default permissions: {e}")
            return 0