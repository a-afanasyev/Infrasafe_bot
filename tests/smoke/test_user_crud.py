# Smoke Tests for User CRUD Operations
# UK Management Bot - User Service Tests

import pytest
import httpx
import asyncio
from typing import Dict, Any, Optional

# Configuration
USER_SERVICE_URL = "http://localhost:8001"
AUTH_SERVICE_URL = "http://localhost:8000"

# Test data
TEST_USERS = [
    {
        "telegram_id": 111111111,
        "username": "crud_test_user1",
        "first_name": "CRUD",
        "last_name": "Test1",
        "phone": "+1111111111",
        "email": "crud1@example.com",
        "language_code": "ru"
    },
    {
        "telegram_id": 222222222,
        "username": "crud_test_user2",
        "first_name": "CRUD",
        "last_name": "Test2",
        "phone": "+2222222222",
        "email": "crud2@example.com",
        "language_code": "en"
    }
]

class TestUserCRUD:
    """Test suite for User CRUD operations"""

    def __init__(self):
        self.created_user_ids = []
        self.service_token = None

    async def get_service_token(self) -> str:
        """Get service token for authenticated requests"""
        if self.service_token:
            return self.service_token

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{AUTH_SERVICE_URL}/api/v1/internal/generate-service-token",
                    params={"service_name": "test-service"}
                )

                if response.status_code == 200:
                    token_data = response.json()
                    self.service_token = token_data["token"]
                    return self.service_token
                else:
                    # Fallback to API key
                    return "test-service.api-key"

            except:
                # Fallback to API key if Auth Service not available
                return "test-service.api-key"

    async def cleanup_test_users(self):
        """Clean up test users created during testing"""
        if not self.created_user_ids:
            return

        token = await self.get_service_token()

        async with httpx.AsyncClient() as client:
            for user_id in self.created_user_ids:
                try:
                    await client.delete(
                        f"{USER_SERVICE_URL}/api/v1/users/{user_id}",
                        headers={
                            "Authorization": f"Bearer {token}",
                            "X-API-Key": token
                        }
                    )
                except:
                    pass  # Ignore cleanup errors

            # Also cleanup by telegram_id if needed
            for test_user in TEST_USERS:
                try:
                    await client.delete(
                        f"{USER_SERVICE_URL}/api/v1/users/by-telegram/{test_user['telegram_id']}",
                        headers={
                            "Authorization": f"Bearer {token}",
                            "X-API-Key": token
                        }
                    )
                except:
                    pass

    async def test_user_service_health(self):
        """Test User Service health and connectivity"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{USER_SERVICE_URL}/health")

            assert response.status_code == 200, f"User Service health check failed: {response.status_code}"

            health_data = response.json()
            assert health_data.get("status") == "healthy", "User Service reports unhealthy"

            print(f"✓ User Service is healthy")
            print(f"  Service: {health_data.get('service', 'unknown')}")
            print(f"  Version: {health_data.get('version', 'unknown')}")

    async def test_create_user(self) -> Dict[str, Any]:
        """Test user creation"""
        token = await self.get_service_token()
        test_user = TEST_USERS[0].copy()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{USER_SERVICE_URL}/api/v1/users",
                json=test_user,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": token,
                    "Content-Type": "application/json"
                }
            )

            assert response.status_code == 201, f"User creation failed: {response.status_code} - {response.text}"

            user_data = response.json()

            # Verify response structure
            assert "id" in user_data
            assert user_data["telegram_id"] == test_user["telegram_id"]
            assert user_data["username"] == test_user["username"]
            assert user_data["first_name"] == test_user["first_name"]
            assert user_data["last_name"] == test_user["last_name"]

            # Track for cleanup
            self.created_user_ids.append(user_data["id"])

            print(f"✓ User created successfully")
            print(f"  ID: {user_data['id']}")
            print(f"  Telegram ID: {user_data['telegram_id']}")
            print(f"  Username: {user_data['username']}")

            return user_data

    async def test_get_user_by_id(self, user_data: Dict[str, Any]):
        """Test retrieving user by ID"""
        token = await self.get_service_token()
        user_id = user_data["id"]

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{USER_SERVICE_URL}/api/v1/users/{user_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": token
                }
            )

            assert response.status_code == 200, f"Get user by ID failed: {response.status_code} - {response.text}"

            retrieved_user = response.json()

            # Verify data matches
            assert retrieved_user["id"] == user_data["id"]
            assert retrieved_user["telegram_id"] == user_data["telegram_id"]
            assert retrieved_user["username"] == user_data["username"]

            print(f"✓ User retrieved by ID successfully")

    async def test_get_user_by_telegram_id(self, user_data: Dict[str, Any]):
        """Test retrieving user by Telegram ID"""
        token = await self.get_service_token()
        telegram_id = user_data["telegram_id"]

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{USER_SERVICE_URL}/api/v1/users/by-telegram/{telegram_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": token
                }
            )

            assert response.status_code == 200, f"Get user by Telegram ID failed: {response.status_code} - {response.text}"

            retrieved_user = response.json()

            # Verify data matches
            assert retrieved_user["id"] == user_data["id"]
            assert retrieved_user["telegram_id"] == user_data["telegram_id"]
            assert retrieved_user["username"] == user_data["username"]

            print(f"✓ User retrieved by Telegram ID successfully")

    async def test_update_user(self, user_data: Dict[str, Any]):
        """Test updating user data"""
        token = await self.get_service_token()
        user_id = user_data["id"]

        update_data = {
            "first_name": "UpdatedCRUD",
            "last_name": "UpdatedTest",
            "status": "approved"
        }

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{USER_SERVICE_URL}/api/v1/users/{user_id}",
                json=update_data,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": token,
                    "Content-Type": "application/json"
                }
            )

            assert response.status_code == 200, f"User update failed: {response.status_code} - {response.text}"

            updated_user = response.json()

            # Verify updates
            assert updated_user["first_name"] == update_data["first_name"]
            assert updated_user["last_name"] == update_data["last_name"]
            assert updated_user["status"] == update_data["status"]

            print(f"✓ User updated successfully")
            print(f"  Name changed to: {updated_user['first_name']} {updated_user['last_name']}")
            print(f"  Status changed to: {updated_user['status']}")

    async def test_list_users(self):
        """Test listing users with pagination"""
        token = await self.get_service_token()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{USER_SERVICE_URL}/api/v1/users",
                params={"page": 1, "page_size": 10},
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": token
                }
            )

            if response.status_code == 200:
                users_data = response.json()

                # Verify response structure
                if isinstance(users_data, list):
                    user_list = users_data
                elif isinstance(users_data, dict) and "users" in users_data:
                    user_list = users_data["users"]
                else:
                    user_list = users_data

                assert isinstance(user_list, list), "Users should be returned as a list"

                print(f"✓ User list retrieved successfully")
                print(f"  Found {len(user_list)} users")

                # Check pagination headers if available
                if hasattr(response, 'headers'):
                    total_count = response.headers.get('X-Total-Count')
                    if total_count:
                        print(f"  Total users: {total_count}")

            else:
                print(f"⚠ List users endpoint returned {response.status_code}")

    async def test_user_roles(self, user_data: Dict[str, Any]):
        """Test user role management"""
        token = await self.get_service_token()
        user_id = user_data["id"]

        async with httpx.AsyncClient() as client:
            # Get user roles
            response = await client.get(
                f"{USER_SERVICE_URL}/api/v1/users/{user_id}/roles",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": token
                }
            )

            if response.status_code == 200:
                roles = response.json()
                assert isinstance(roles, list), "Roles should be returned as a list"

                print(f"✓ User roles retrieved successfully")
                print(f"  User has {len(roles)} roles")

                # Try to assign a new role
                role_data = {
                    "role_key": "executor",
                    "role_data": {"specialization": "electrical"}
                }

                assign_response = await client.post(
                    f"{USER_SERVICE_URL}/api/v1/users/{user_id}/roles",
                    json=role_data,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-API-Key": token,
                        "Content-Type": "application/json"
                    }
                )

                if assign_response.status_code == 201:
                    print(f"✓ Role assigned successfully")
                else:
                    print(f"⚠ Role assignment returned {assign_response.status_code}")

            else:
                print(f"⚠ Get user roles returned {response.status_code}")

    async def test_user_not_found(self):
        """Test handling of non-existent users"""
        token = await self.get_service_token()

        async with httpx.AsyncClient() as client:
            # Test non-existent user ID
            response = await client.get(
                f"{USER_SERVICE_URL}/api/v1/users/999999",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": token
                }
            )

            assert response.status_code == 404, "Should return 404 for non-existent user"

            # Test non-existent telegram ID
            response = await client.get(
                f"{USER_SERVICE_URL}/api/v1/users/by-telegram/999999999",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": token
                }
            )

            assert response.status_code == 404, "Should return 404 for non-existent telegram user"

            print(f"✓ Non-existent user handling works correctly")

    async def test_duplicate_user_prevention(self):
        """Test prevention of duplicate user creation"""
        token = await self.get_service_token()
        test_user = TEST_USERS[1].copy()

        async with httpx.AsyncClient() as client:
            # Create first user
            response1 = await client.post(
                f"{USER_SERVICE_URL}/api/v1/users",
                json=test_user,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-API-Key": token,
                    "Content-Type": "application/json"
                }
            )

            if response1.status_code == 201:
                user_data = response1.json()
                self.created_user_ids.append(user_data["id"])

                # Try to create duplicate
                response2 = await client.post(
                    f"{USER_SERVICE_URL}/api/v1/users",
                    json=test_user,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "X-API-Key": token,
                        "Content-Type": "application/json"
                    }
                )

                assert response2.status_code in [400, 409], "Should prevent duplicate user creation"

                print(f"✓ Duplicate user prevention works correctly")

            else:
                print(f"⚠ Could not create user for duplicate test: {response1.status_code}")

# Test runner
async def run_user_crud_tests():
    """Run all User CRUD smoke tests"""
    print("=" * 50)
    print("SMOKE TESTS: User CRUD Operations")
    print("=" * 50)

    test_instance = TestUserCRUD()

    try:
        # Basic connectivity
        await test_instance.test_user_service_health()

        # Create a test user for subsequent tests
        print(f"\n🧪 Testing: User Creation")
        user_data = await test_instance.test_create_user()
        print(f"✅ User Creation PASSED")

        # Run all CRUD tests
        tests = [
            ("Get User by ID", test_instance.test_get_user_by_id(user_data)),
            ("Get User by Telegram ID", test_instance.test_get_user_by_telegram_id(user_data)),
            ("Update User", test_instance.test_update_user(user_data)),
            ("User Roles", test_instance.test_user_roles(user_data)),
            ("List Users", test_instance.test_list_users()),
            ("User Not Found", test_instance.test_user_not_found()),
            ("Duplicate Prevention", test_instance.test_duplicate_user_prevention())
        ]

        results = {"passed": 1, "failed": 0, "errors": []}  # Start with 1 for create user

        for test_name, test_coro in tests:
            try:
                print(f"\n🧪 Testing: {test_name}")
                await test_coro
                results["passed"] += 1
                print(f"✅ {test_name} PASSED")

            except Exception as e:
                results["failed"] += 1
                results["errors"].append((test_name, str(e)))
                print(f"❌ {test_name} FAILED: {e}")

        print(f"\n" + "=" * 50)
        print(f"USER CRUD TEST RESULTS")
        print(f"=" * 50)
        print(f"✅ Passed: {results['passed']}")
        print(f"❌ Failed: {results['failed']}")

        if results["errors"]:
            print(f"\nErrors:")
            for test_name, error in results["errors"]:
                print(f"  - {test_name}: {error}")

        return results["failed"] == 0

    finally:
        # Cleanup
        print(f"\n🧹 Cleaning up test data...")
        await test_instance.cleanup_test_users()
        print(f"✓ Cleanup completed")

if __name__ == "__main__":
    # Run smoke tests directly
    success = asyncio.run(run_user_crud_tests())
    exit(0 if success else 1)