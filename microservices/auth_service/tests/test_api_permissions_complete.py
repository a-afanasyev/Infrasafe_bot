# Complete API Tests for permissions.py - 100% Coverage
# UK Management Bot - Auth Service

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
class TestPermissionsAPIComplete:
    """Complete test coverage for all permissions API endpoints"""

    # GET /api/v1/permissions/
    async def test_get_permissions_list_success(self, client: AsyncClient):
        """Test getting list of permissions"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.get_permissions = AsyncMock(return_value=[
                MagicMock(permission_key="users:read"),
                MagicMock(permission_key="users:write")
            ])

            response = await client.get("/api/v1/permissions/")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    async def test_get_permissions_list_error(self, client: AsyncClient):
        """Test get permissions error handling"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.get_permissions = AsyncMock(side_effect=Exception("Service error"))

            response = await client.get("/api/v1/permissions/")

            assert response.status_code == 500

    # POST /api/v1/permissions/
    async def test_create_permission_success(self, client: AsyncClient):
        """Test creating new permission"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            new_perm = MagicMock()
            new_perm.permission_key = "test:read"
            mock_instance.create_permission = AsyncMock(return_value=new_perm)

            response = await client.post("/api/v1/permissions/", json={
                "permission_key": "test:read",
                "permission_name": "Test Read",
                "description": "Test permission",
                "service_name": "test-service",
                "resource_type": "test"
            })

            assert response.status_code == 200
            data = response.json()
            assert "permission_key" in data

    async def test_create_permission_error(self, client: AsyncClient):
        """Test create permission error handling"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.create_permission = AsyncMock(side_effect=Exception("Create error"))

            response = await client.post("/api/v1/permissions/", json={
                "permission_key": "test:read",
                "permission_name": "Test"
            })

            assert response.status_code == 500

    # GET /api/v1/permissions/{permission_id}
    async def test_get_permission_success(self, client: AsyncClient):
        """Test getting single permission"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            perm_mock = MagicMock()
            perm_mock.id = 1
            mock_instance.get_permission = AsyncMock(return_value=perm_mock)

            response = await client.get("/api/v1/permissions/1")

            assert response.status_code == 200

    async def test_get_permission_not_found(self, client: AsyncClient):
        """Test getting non-existent permission"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.get_permission = AsyncMock(return_value=None)

            response = await client.get("/api/v1/permissions/99999")

            assert response.status_code == 404

    async def test_get_permission_error(self, client: AsyncClient):
        """Test get permission error handling"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.get_permission = AsyncMock(side_effect=Exception("Get error"))

            response = await client.get("/api/v1/permissions/1")

            assert response.status_code == 500

    # PATCH /api/v1/permissions/{permission_id}
    async def test_update_permission_success(self, client: AsyncClient):
        """Test updating permission"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            updated_perm = MagicMock()
            updated_perm.id = 1
            mock_instance.update_permission = AsyncMock(return_value=updated_perm)

            response = await client.patch("/api/v1/permissions/1", json={
                "permission_name": "Updated Name"
            })

            assert response.status_code == 200

    async def test_update_permission_not_found(self, client: AsyncClient):
        """Test updating non-existent permission"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.update_permission = AsyncMock(return_value=None)

            response = await client.patch("/api/v1/permissions/99999", json={
                "permission_name": "Updated"
            })

            assert response.status_code == 404

    async def test_update_permission_error(self, client: AsyncClient):
        """Test update permission error handling"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.update_permission = AsyncMock(side_effect=Exception("Update error"))

            response = await client.patch("/api/v1/permissions/1", json={
                "permission_name": "Test"
            })

            assert response.status_code == 500

    # GET /api/v1/permissions/users/{user_id}/roles
    async def test_get_user_roles_success(self, client: AsyncClient):
        """Test getting user roles"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.get_user_roles = AsyncMock(return_value=[
                MagicMock(role_key="admin")
            ])

            response = await client.get("/api/v1/permissions/users/123/roles")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    async def test_get_user_roles_error(self, client: AsyncClient):
        """Test get user roles error handling"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.get_user_roles = AsyncMock(side_effect=Exception("Roles error"))

            response = await client.get("/api/v1/permissions/users/123/roles")

            assert response.status_code == 500

    # POST /api/v1/permissions/users/{user_id}/roles
    async def test_assign_user_role_success(self, client: AsyncClient):
        """Test assigning role to user"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            role_mock = MagicMock()
            role_mock.role_key = "admin"
            mock_instance.assign_user_role = AsyncMock(return_value=role_mock)

            response = await client.post("/api/v1/permissions/users/123/roles", json={
                "role_key": "admin",
                "granted_by": 1
            })

            assert response.status_code == 200

    async def test_assign_user_role_error(self, client: AsyncClient):
        """Test assign user role error handling"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.assign_user_role = AsyncMock(side_effect=Exception("Assign error"))

            response = await client.post("/api/v1/permissions/users/123/roles", json={
                "role_key": "admin"
            })

            assert response.status_code == 500

    # PATCH /api/v1/permissions/users/{user_id}/roles/{role_id}
    async def test_update_user_role_success(self, client: AsyncClient):
        """Test updating user role"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            updated_role = MagicMock()
            updated_role.id = 1
            mock_instance.update_user_role = AsyncMock(return_value=updated_role)

            response = await client.patch("/api/v1/permissions/users/123/roles/1", json={
                "is_active": False
            })

            assert response.status_code == 200

    async def test_update_user_role_not_found(self, client: AsyncClient):
        """Test updating non-existent user role"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.update_user_role = AsyncMock(return_value=None)

            response = await client.patch("/api/v1/permissions/users/123/roles/99999", json={
                "is_active": False
            })

            assert response.status_code == 404

    async def test_update_user_role_error(self, client: AsyncClient):
        """Test update user role error handling"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.update_user_role = AsyncMock(side_effect=Exception("Update error"))

            response = await client.patch("/api/v1/permissions/users/123/roles/1", json={})

            assert response.status_code == 500

    # DELETE /api/v1/permissions/users/{user_id}/roles/{role_id}
    async def test_remove_user_role_success(self, client: AsyncClient):
        """Test removing user role"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.remove_user_role = AsyncMock(return_value=True)

            response = await client.delete("/api/v1/permissions/users/123/roles/1")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    async def test_remove_user_role_not_found(self, client: AsyncClient):
        """Test removing non-existent user role"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.remove_user_role = AsyncMock(return_value=False)

            response = await client.delete("/api/v1/permissions/users/123/roles/99999")

            assert response.status_code == 404

    async def test_remove_user_role_error(self, client: AsyncClient):
        """Test remove user role error handling"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.remove_user_role = AsyncMock(side_effect=Exception("Remove error"))

            response = await client.delete("/api/v1/permissions/users/123/roles/1")

            assert response.status_code == 500

    # POST /api/v1/permissions/check
    async def test_check_permission_success(self, client: AsyncClient):
        """Test checking user permission"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.check_user_permission = AsyncMock(return_value=True)

            response = await client.post("/api/v1/permissions/check", json={
                "user_id": 123,
                "permission_key": "users:read"
            })

            assert response.status_code == 200
            data = response.json()
            assert data["has_permission"] is True

    async def test_check_permission_denied(self, client: AsyncClient):
        """Test permission check denied"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.check_user_permission = AsyncMock(return_value=False)

            response = await client.post("/api/v1/permissions/check", json={
                "user_id": 123,
                "permission_key": "admin:write"
            })

            assert response.status_code == 200
            data = response.json()
            assert data["has_permission"] is False

    async def test_check_permission_error(self, client: AsyncClient):
        """Test check permission error handling"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.check_user_permission = AsyncMock(side_effect=Exception("Check error"))

            response = await client.post("/api/v1/permissions/check", json={
                "user_id": 123,
                "permission_key": "test:read"
            })

            assert response.status_code == 500

    # GET /api/v1/permissions/users/{user_id}/permissions
    async def test_get_user_effective_permissions_success(self, client: AsyncClient):
        """Test getting user effective permissions"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.get_user_effective_permissions = AsyncMock(return_value=[
                "users:read", "users:write"
            ])

            response = await client.get("/api/v1/permissions/users/123/permissions")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data["permissions"], list)

    async def test_get_user_effective_permissions_error(self, client: AsyncClient):
        """Test get effective permissions error handling"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.get_user_effective_permissions = AsyncMock(side_effect=Exception("Perm error"))

            response = await client.get("/api/v1/permissions/users/123/permissions")

            assert response.status_code == 500

    # Rate limit endpoints (4 endpoints)
    async def test_get_rate_limit_clients_success(self, client: AsyncClient):
        """Test getting rate limit clients"""
        response = await client.get("/api/v1/permissions/rate-limit/clients")
        assert response.status_code == 200

    async def test_get_rate_limit_client_success(self, client: AsyncClient):
        """Test getting specific client rate limit"""
        response = await client.get("/api/v1/permissions/rate-limit/client/192.168.1.1")
        assert response.status_code == 200

    async def test_delete_rate_limit_client_success(self, client: AsyncClient):
        """Test deleting client rate limit"""
        response = await client.delete("/api/v1/permissions/rate-limit/client/192.168.1.1")
        assert response.status_code == 200

    async def test_cleanup_rate_limits_success(self, client: AsyncClient):
        """Test cleanup of rate limits"""
        response = await client.post("/api/v1/permissions/rate-limit/cleanup")
        assert response.status_code == 200

    # POST /api/v1/permissions/initialize-defaults
    async def test_initialize_defaults_success(self, client: AsyncClient):
        """Test initializing default permissions"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.initialize_default_permissions = AsyncMock(return_value=10)

            response = await client.post("/api/v1/permissions/initialize-defaults")

            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 10

    async def test_initialize_defaults_error(self, client: AsyncClient):
        """Test initialize defaults error handling"""
        with patch('api.v1.permissions.PermissionService') as mock_perm:
            mock_instance = mock_perm.return_value
            mock_instance.initialize_default_permissions = AsyncMock(side_effect=Exception("Init error"))

            response = await client.post("/api/v1/permissions/initialize-defaults")

            assert response.status_code == 500
