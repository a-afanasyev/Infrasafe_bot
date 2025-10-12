# Test Permission Service - Extended Coverage
# UK Management Bot - Auth Service Tests

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from services.permission_service import PermissionService
from schemas.auth import PermissionCreate, PermissionResponse

@pytest.mark.asyncio
class TestPermissionServiceExtended:
    """Extended test cases for Permission Service to increase coverage"""

    @pytest.fixture
    def permission_service(self, db_session):
        """Permission service fixture"""
        return PermissionService(db_session)

    @pytest.fixture
    def sample_permission_data(self):
        """Sample permission data for tests"""
        return PermissionCreate(
            permission_key="users:delete",
            permission_name="Delete Users",
            description="Permission to delete users",
            service_name="user-service",
            resource_type="user",
            is_active=True,
            is_system=False
        )

    async def test_create_permission_success(self, permission_service, db_session, sample_permission_data):
        """Test successful permission creation"""
        result = await permission_service.create_permission(sample_permission_data)

        assert result is not None
        assert result.permission_key == sample_permission_data.permission_key
        assert result.permission_name == sample_permission_data.permission_name
        assert result.is_active is True

    async def test_create_permission_duplicate(self, permission_service, db_session, sample_permission_data):
        """Test creating duplicate permission raises error"""
        # Create first permission
        await permission_service.create_permission(sample_permission_data)

        # Try to create duplicate
        with pytest.raises(ValueError):
            await permission_service.create_permission(sample_permission_data)

    async def test_get_permission_by_id(self, permission_service, db_session, sample_permission_data):
        """Test getting permission by ID"""
        # Create permission
        created = await permission_service.create_permission(sample_permission_data)

        # Get by ID
        result = await permission_service.get_permission(created.id)

        assert result is not None
        assert result.id == created.id
        assert result.permission_key == sample_permission_data.permission_key

    async def test_get_permission_not_found(self, permission_service, db_session):
        """Test getting non-existent permission"""
        result = await permission_service.get_permission(99999)

        assert result is None

    async def test_get_permissions_list(self, permission_service, db_session, sample_permission_data):
        """Test getting list of permissions"""
        # Create some permissions
        await permission_service.create_permission(sample_permission_data)

        perm2 = PermissionCreate(
            permission_key="users:update",
            permission_name="Update Users",
            description="Permission to update users",
            service_name="user-service",
            resource_type="user",
            is_active=True,
            is_system=False
        )
        await permission_service.create_permission(perm2)

        # Get all permissions
        results = await permission_service.get_permissions()

        assert len(results) >= 2
        keys = [p.permission_key for p in results]
        assert "users:delete" in keys
        assert "users:update" in keys

    async def test_get_permissions_with_filters(self, permission_service, db_session):
        """Test getting permissions with service filter"""
        # Create permissions for different services
        perm1 = PermissionCreate(
            permission_key="test:read",
            permission_name="Test Read",
            description="Test permission",
            service_name="test-service",
            resource_type="test",
            is_active=True,
            is_system=False
        )
        await permission_service.create_permission(perm1)

        # Get filtered by service
        results = await permission_service.get_permissions(service_name="test-service")

        assert len(results) >= 1
        assert all(p.service_name == "test-service" for p in results)

    async def test_update_permission(self, permission_service, db_session, sample_permission_data):
        """Test updating permission"""
        # Create permission
        created = await permission_service.create_permission(sample_permission_data)

        # Update it
        update_data = {
            "permission_name": "Delete Users (Updated)",
            "description": "Updated description",
            "is_active": False
        }

        updated = await permission_service.update_permission(created.id, update_data)

        assert updated is not None
        assert updated.permission_name == "Delete Users (Updated)"
        assert updated.description == "Updated description"
        assert updated.is_active is False

    async def test_update_permission_not_found(self, permission_service, db_session):
        """Test updating non-existent permission"""
        result = await permission_service.update_permission(99999, {"permission_name": "Test"})

        assert result is None

    async def test_get_user_roles_empty(self, permission_service, db_session):
        """Test getting roles for user with no roles"""
        roles = await permission_service.get_user_roles(user_id=99999)

        assert isinstance(roles, list)
        assert len(roles) == 0

    async def test_assign_user_role(self, permission_service, db_session):
        """Test assigning role to user"""
        role_data = {
            "role_key": "admin",
            "role_name": "Administrator",
            "granted_by": 1,
            "is_active": True
        }

        result = await permission_service.assign_user_role(user_id=123, role_data=role_data)

        assert result is not None
        assert result.user_id == 123
        assert result.role_key == "admin"
        assert result.is_active is True

    async def test_check_user_permission_no_roles(self, permission_service, db_session):
        """Test permission check for user without roles"""
        has_permission = await permission_service.check_user_permission(
            user_id=99999,
            permission_key="users:read"
        )

        assert has_permission is False

    async def test_get_user_effective_permissions_empty(self, permission_service, db_session):
        """Test getting effective permissions for user with no roles"""
        permissions = await permission_service.get_user_effective_permissions(user_id=99999)

        assert isinstance(permissions, list)
        assert len(permissions) == 0

    async def test_initialize_default_permissions(self, permission_service, db_session):
        """Test initializing default permissions"""
        count = await permission_service.initialize_default_permissions()

        assert isinstance(count, int)
        assert count >= 0

    async def test_remove_user_role(self, permission_service, db_session):
        """Test removing user role"""
        # First assign a role
        role_data = {
            "role_key": "test_role",
            "role_name": "Test Role",
            "granted_by": 1,
            "is_active": True
        }
        assigned = await permission_service.assign_user_role(user_id=123, role_data=role_data)

        # Then remove it
        result = await permission_service.remove_user_role(user_id=123, role_id=assigned.id)

        assert result is True

    async def test_remove_user_role_not_found(self, permission_service, db_session):
        """Test removing non-existent role"""
        result = await permission_service.remove_user_role(user_id=123, role_id=99999)

        assert result is False

    async def test_update_user_role(self, permission_service, db_session):
        """Test updating user role"""
        # First assign a role
        role_data = {
            "role_key": "test_role",
            "role_name": "Test Role",
            "granted_by": 1,
            "is_active": True
        }
        assigned = await permission_service.assign_user_role(user_id=123, role_data=role_data)

        # Update it
        update_data = {"is_active": False}
        updated = await permission_service.update_user_role(user_id=123, role_id=assigned.id, update_data=update_data)

        assert updated is not None
        assert updated.is_active is False

    async def test_get_user_roles_active_only(self, permission_service, db_session):
        """Test getting only active user roles"""
        # Assign roles
        role1 = {
            "role_key": "active_role",
            "role_name": "Active Role",
            "granted_by": 1,
            "is_active": True
        }
        await permission_service.assign_user_role(user_id=456, role_data=role1)

        role2 = {
            "role_key": "inactive_role",
            "role_name": "Inactive Role",
            "granted_by": 1,
            "is_active": False
        }
        await permission_service.assign_user_role(user_id=456, role_data=role2)

        # Get active only
        active_roles = await permission_service.get_user_roles(user_id=456, active_only=True)

        assert len(active_roles) >= 1
        assert all(role.is_active for role in active_roles)
