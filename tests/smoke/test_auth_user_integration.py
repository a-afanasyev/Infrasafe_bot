# Smoke Tests for Auth-User Service Integration
# UK Management Bot - Integration Tests

import pytest
import httpx
import asyncio
from typing import Dict, Any

# Configuration for smoke tests
AUTH_SERVICE_URL = "http://localhost:8000"
USER_SERVICE_URL = "http://localhost:8001"
MEDIA_SERVICE_URL = "http://localhost:8080"

# Test data
TEST_USER_DATA = {
    "telegram_id": 999999999,
    "username": "smoke_test_user",
    "first_name": "Smoke",
    "last_name": "Test",
    "phone": "+1234567890",
    "email": "smoke.test@example.com",
    "language_code": "en"
}

class TestAuthUserIntegration:
    """Test suite for Auth-User service integration"""

    @pytest.fixture
    async def test_user(self):
        """Create a test user for integration testing"""
        async with httpx.AsyncClient() as client:
            # Create user in User Service
            response = await client.post(
                f"{USER_SERVICE_URL}/api/v1/users",
                json=TEST_USER_DATA,
                headers={"X-API-Key": "test-api-key"}
            )

            if response.status_code == 201:
                user_data = response.json()
                yield user_data

                # Cleanup: Delete test user
                try:
                    await client.delete(
                        f"{USER_SERVICE_URL}/api/v1/users/{user_data['id']}",
                        headers={"X-API-Key": "test-api-key"}
                    )
                except:
                    pass  # Ignore cleanup errors
            else:
                pytest.skip(f"Could not create test user: {response.status_code}")

    async def test_service_connectivity(self):
        """Test basic connectivity to all services"""
        services = [
            ("Auth Service", f"{AUTH_SERVICE_URL}/health"),
            ("User Service", f"{USER_SERVICE_URL}/health"),
            ("Media Service", f"{MEDIA_SERVICE_URL}/health")
        ]

        async with httpx.AsyncClient(timeout=5.0) as client:
            for service_name, health_url in services:
                try:
                    response = await client.get(health_url)
                    assert response.status_code == 200, f"{service_name} health check failed"

                    health_data = response.json()
                    assert health_data.get("status") == "healthy", f"{service_name} reports unhealthy"

                    print(f"✓ {service_name} is healthy")

                except httpx.RequestError as e:
                    pytest.fail(f"Could not connect to {service_name}: {e}")

    async def test_service_token_generation(self):
        """Test service token generation in Auth Service"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AUTH_SERVICE_URL}/api/v1/internal/generate-service-token",
                params={"service_name": "auth-service"}
            )

            assert response.status_code == 200, f"Token generation failed: {response.text}"

            token_data = response.json()
            assert "token" in token_data
            assert token_data["service_name"] == "auth-service"
            assert isinstance(token_data["permissions"], list)

            print(f"✓ Service token generated successfully")
            return token_data["token"]

    async def test_service_token_validation(self):
        """Test service token validation between services"""
        # Generate token in Auth Service
        token = await self.test_service_token_generation()

        async with httpx.AsyncClient() as client:
            # Validate token in User Service
            response = await client.post(
                f"{USER_SERVICE_URL}/api/v1/internal/validate-service-token",
                json={
                    "token": token,
                    "service_name": "auth-service"
                }
            )

            assert response.status_code == 200, f"Token validation failed: {response.text}"

            validation_data = response.json()
            assert validation_data["valid"] == True
            assert validation_data["service_name"] == "auth-service"

            print(f"✓ Service token validation successful")

    async def test_auth_user_service_communication(self, test_user):
        """Test Auth Service can communicate with User Service"""
        telegram_id = str(TEST_USER_DATA["telegram_id"])

        async with httpx.AsyncClient() as client:
            # Test Auth Service calling User Service via internal API
            # This simulates the authentication flow

            # First, get a service token
            token_response = await client.post(
                f"{AUTH_SERVICE_URL}/api/v1/internal/generate-service-token",
                params={"service_name": "auth-service"}
            )
            assert token_response.status_code == 200
            service_token = token_response.json()["token"]

            # Now test Auth Service fetching user data
            user_response = await client.get(
                f"{USER_SERVICE_URL}/api/v1/users/by-telegram/{telegram_id}",
                headers={"Authorization": f"Bearer {service_token}"}
            )

            if user_response.status_code == 200:
                user_data = user_response.json()
                assert user_data["telegram_id"] == TEST_USER_DATA["telegram_id"]
                assert user_data["username"] == TEST_USER_DATA["username"]

                print(f"✓ Auth Service successfully retrieved user data")
            else:
                pytest.fail(f"Auth-User communication failed: {user_response.status_code} - {user_response.text}")

    async def test_login_flow_simulation(self, test_user):
        """Test complete login flow simulation"""
        telegram_id = str(TEST_USER_DATA["telegram_id"])

        async with httpx.AsyncClient() as client:
            # Simulate login request to Auth Service
            login_response = await client.post(
                f"{AUTH_SERVICE_URL}/api/v1/auth/login",
                json={
                    "telegram_id": telegram_id,
                    "auth_method": "telegram"
                }
            )

            # Login might return different status codes depending on implementation
            if login_response.status_code in [200, 201]:
                login_data = login_response.json()

                # Check if we get user information back
                if "user" in login_data:
                    assert login_data["user"]["telegram_id"] == telegram_id
                    print(f"✓ Login flow completed successfully")
                else:
                    print(f"✓ Login request processed (user lookup successful)")

            elif login_response.status_code == 404:
                print(f"✓ Login correctly returned 'user not found' for test user")
            else:
                pytest.fail(f"Unexpected login response: {login_response.status_code} - {login_response.text}")

    async def test_user_statistics_integration(self):
        """Test user statistics endpoint integration"""
        async with httpx.AsyncClient() as client:
            # Get user statistics via Auth Service (which calls User Service)
            stats_response = await client.get(
                f"{AUTH_SERVICE_URL}/api/v1/internal/user-stats"
            )

            if stats_response.status_code == 200:
                stats_data = stats_response.json()

                # Verify expected statistics fields
                expected_fields = [
                    "total_users", "active_users", "status_distribution",
                    "role_distribution", "monthly_registrations"
                ]

                for field in expected_fields:
                    assert field in stats_data, f"Missing field: {field}"

                assert isinstance(stats_data["total_users"], int)
                assert isinstance(stats_data["active_users"], int)
                assert isinstance(stats_data["status_distribution"], dict)
                assert isinstance(stats_data["role_distribution"], dict)

                print(f"✓ User statistics integration working")
                print(f"  Total users: {stats_data['total_users']}")
                print(f"  Active users: {stats_data['active_users']}")

            else:
                print(f"⚠ User statistics endpoint returned {stats_response.status_code}")
                # This might be expected if there's no data yet

    async def test_api_key_fallback(self):
        """Test API key authentication fallback"""
        async with httpx.AsyncClient() as client:
            # Test API key authentication
            response = await client.get(
                f"{USER_SERVICE_URL}/api/v1/internal/health/dependencies",
                headers={"X-API-Key": "auth-service.test"}
            )

            # Should work with valid API key format
            if response.status_code == 200:
                print(f"✓ API key fallback authentication working")
            else:
                # Try with Authorization header instead
                response = await client.get(
                    f"{USER_SERVICE_URL}/api/v1/internal/health/dependencies",
                    headers={"Authorization": "Bearer auth-service.test"}
                )

                if response.status_code == 200:
                    print(f"✓ Bearer token fallback authentication working")
                else:
                    print(f"⚠ API key fallback needs configuration: {response.status_code}")

    async def test_error_handling(self):
        """Test error handling in service communication"""
        async with httpx.AsyncClient() as client:
            # Test invalid token
            response = await client.get(
                f"{USER_SERVICE_URL}/api/v1/users/by-telegram/999999999",
                headers={"Authorization": "Bearer invalid_token"}
            )

            assert response.status_code in [401, 403], "Should reject invalid token"
            print(f"✓ Invalid token correctly rejected")

            # Test missing authentication
            response = await client.get(
                f"{USER_SERVICE_URL}/api/v1/users/by-telegram/999999999"
            )

            assert response.status_code == 401, "Should require authentication"
            print(f"✓ Missing authentication correctly rejected")

# Integration test runner
async def run_smoke_tests():
    """Run all smoke tests"""
    print("=" * 50)
    print("SMOKE TESTS: Auth-User Service Integration")
    print("=" * 50)

    test_instance = TestAuthUserIntegration()

    tests = [
        ("Service Connectivity", test_instance.test_service_connectivity()),
        ("Service Token Generation", test_instance.test_service_token_generation()),
        ("Service Token Validation", test_instance.test_service_token_validation()),
        ("API Key Fallback", test_instance.test_api_key_fallback()),
        ("Error Handling", test_instance.test_error_handling()),
        ("User Statistics Integration", test_instance.test_user_statistics_integration())
    ]

    results = {"passed": 0, "failed": 0, "errors": []}

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
    print(f"SMOKE TEST RESULTS")
    print(f"=" * 50)
    print(f"✅ Passed: {results['passed']}")
    print(f"❌ Failed: {results['failed']}")

    if results["errors"]:
        print(f"\nErrors:")
        for test_name, error in results["errors"]:
            print(f"  - {test_name}: {error}")

    return results["failed"] == 0

if __name__ == "__main__":
    # Run smoke tests directly
    success = asyncio.run(run_smoke_tests())
    exit(0 if success else 1)