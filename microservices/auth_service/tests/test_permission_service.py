# Test Permission Service
# UK Management Bot - Auth Service Tests

import pytest
import pytest_asyncio
from datetime import datetime, timedelta

from services.permission_service import PermissionService
from models.auth import Permission, UserRole
from schemas.auth import PermissionCreate

@pytest.mark.asyncio
class TestPermissionService:
    """Test cases for Permission Service"""

    @pytest_asyncio.fixture
    def sample_permission_data(self):
        """Sample permission data for testing"""
        return {
            "permission_key": "test:read",
            "permission_name": "Test Read Permission",
            "description": "Test read permission",
            "service_name": "test-service",
            "resource_type": "test",
            "is_active": True,
            "is_system": False
        }

    @pytest_asyncio.fixture
    def sample_role_data(self):
        """Sample role data for testing"""
        return {
            "role": "tester",
            "assigned_by": 1,
            "is_active": True
        }

    async def test_create_permission(self, permission_service, db_session, sample_permission_data):
        """Test creating a new permission"""
        # Create permission (convert dict to pydantic model)
        permission_create = PermissionCreate(**sample_permission_data)
        permission = await permission_service.create_permission(permission_create)

        assert permission is not None
        assert permission.permission_key == sample_permission_data["permission_key"]
        assert permission.permission_name == sample_permission_data["permission_name"]
        assert permission.description == sample_permission_data["description"]
        assert permission.service_name == sample_permission_data["service_name"]

    async def test_get_permission(self, permission_service, db_session, sample_permission_data):
        """Test getting permission by ID"""
        # Create permission first
        permission_create = PermissionCreate(**sample_permission_data)
        created_permission = await permission_service.create_permission(permission_create)
        permission_id = created_permission.id

        # Get permission
        permission = await permission_service.get_permission(permission_id)

        assert permission is not None
        assert permission.id == permission_id
        assert permission.permission_key == sample_permission_data["permission_key"]

    async def test_get_permission_not_found(self, permission_service):
        """Test getting non-existent permission"""
        permission = await permission_service.get_permission(99999)
        assert permission is None

    async def test_get_permissions_list(self, permission_service, db_session, sample_permission_data):
        """Test getting list of permissions"""
        # Create multiple permissions
        await permission_service.create_permission(PermissionCreate(**sample_permission_data))
        await permission_service.create_permission(PermissionCreate(**{
            "permission_key": "test:write",
            "permission_name": "Test Write Permission",
            "description": "Test write permission",
            "service_name": "test-service",
            "resource_type": "test"
        }))

        # Get all permissions
        permissions = await permission_service.get_permissions()

        assert len(permissions) >= 2
        assert any(p.permission_key == "test:read" for p in permissions)
        assert any(p.permission_key == "test:write" for p in permissions)

    async def test_get_permissions_with_filters(self, permission_service, db_session, sample_permission_data):
        """Test getting permissions with filters"""
        # Create permissions
        await permission_service.create_permission(PermissionCreate(**sample_permission_data))
        await permission_service.create_permission(PermissionCreate(**{
            "permission_key": "other:read",
            "permission_name": "Other Read Permission",
            "description": "Other read permission",
            "service_name": "other-service",
            "resource_type": "other"
        }))

        # Get filtered permissions by service
        permissions = await permission_service.get_permissions(service_name="test-service")

        assert len(permissions) >= 1
        assert all(p.service_name == "test-service" for p in permissions)

    async def test_assign_user_role(self, permission_service, db_session, sample_role_data):
        """Test assigning role to user"""
        user_id = 123

        # Assign role
        user_role = await permission_service.assign_user_role(user_id, sample_role_data)

        assert user_role is not None
        assert user_role.user_id == user_id
        assert user_role.role == sample_role_data["role"]
        assert user_role.is_active is True

    async def test_get_user_roles(self, permission_service, db_session, sample_role_data):
        """Test getting user roles"""
        user_id = 123

        # Assign multiple roles
        await permission_service.assign_user_role(user_id, sample_role_data)
        await permission_service.assign_user_role(user_id, {
            "role": "admin",
            "assigned_by": 1,
            "is_active": True
        })

        # Get user roles
        roles = await permission_service.get_user_roles(user_id)

        assert len(roles) >= 2
        assert any(r.role == "tester" for r in roles)
        assert any(r.role == "admin" for r in roles)

    async def test_get_user_roles_active_only(self, permission_service, db_session, sample_role_data):
        """Test getting only active user roles"""
        user_id = 123

        # Assign active role
        active_role = await permission_service.assign_user_role(user_id, sample_role_data)

        # Assign inactive role
        inactive_role_data = {**sample_role_data, "role": "inactive_role", "is_active": False}
        await permission_service.assign_user_role(user_id, inactive_role_data)

        # Get active roles only
        active_roles = await permission_service.get_user_roles(user_id, active_only=True)

        # Get all roles
        all_roles = await permission_service.get_user_roles(user_id, active_only=False)

        assert len(active_roles) < len(all_roles)
        assert all(r.is_active for r in active_roles)

    async def test_remove_user_role(self, permission_service, db_session, sample_role_data):
        """Test removing user role"""
        user_id = 123

        # Assign role
        user_role = await permission_service.assign_user_role(user_id, sample_role_data)
        role_id = user_role.id

        # Remove role
        result = await permission_service.remove_user_role(user_id, role_id)

        assert result is True

        # Verify role removed
        roles = await permission_service.get_user_roles(user_id, active_only=True)
        assert not any(r.id == role_id for r in roles)

    async def test_update_user_role(self, permission_service, db_session, sample_role_data):
        """Test updating user role"""
        user_id = 123

        # Assign role
        user_role = await permission_service.assign_user_role(user_id, sample_role_data)
        role_id = user_role.id

        # Update role
        updated_role = await permission_service.update_user_role(
            user_id,
            role_id,
            {"is_active": False}
        )

        assert updated_role is not None
        assert updated_role.is_active is False

    async def test_check_user_permission(self, permission_service, db_session, sample_permission_data, sample_role_data):
        """Test checking if user has permission"""
        user_id = 123

        # Create permission
        permission = await permission_service.create_permission(PermissionCreate(**sample_permission_data))

        # This test would need role-permission mapping setup
        # For now, just test the method exists and runs
        has_permission = await permission_service.check_user_permission(
            user_id,
            sample_permission_data["permission_key"]
        )

        # Without role-permission mapping, should return False
        assert has_permission is False

    async def test_get_user_effective_permissions(self, permission_service, db_session, sample_role_data):
        """Test getting user's effective permissions"""
        user_id = 123

        # Assign role
        await permission_service.assign_user_role(user_id, sample_role_data)

        # Get effective permissions
        permissions = await permission_service.get_user_effective_permissions(user_id)

        # Should return list (may be empty without role-permission mapping)
        assert isinstance(permissions, list)

    async def test_initialize_default_permissions(self, permission_service, db_session):
        """Test initializing default permissions"""
        # Initialize default permissions
        count = await permission_service.initialize_default_permissions()

        # Should create some default permissions
        assert count > 0

        # Verify permissions were created
        permissions = await permission_service.get_permissions()
        assert len(permissions) >= count

    async def test_update_permission(self, permission_service, db_session, sample_permission_data):
        """Test updating permission"""
        # Create permission
        permission = await permission_service.create_permission(PermissionCreate(**sample_permission_data))
        permission_id = permission.id

        # Update permission
        updated_permission = await permission_service.update_permission(
            permission_id,
            {"description": "Updated description"}
        )

        assert updated_permission is not None
        assert updated_permission.description == "Updated description"
