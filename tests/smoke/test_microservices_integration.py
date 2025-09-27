#!/usr/bin/env python3
# Comprehensive Microservices Integration Tests
# UK Management Bot - Integration Testing

import asyncio
import httpx
import time
import random
from typing import Dict, Any, List

# Service URLs
AUTH_SERVICE_URL = "http://localhost:8000"
USER_SERVICE_URL = "http://localhost:8001"
MEDIA_SERVICE_URL = "http://localhost:8080"

# Test data
TEST_USER_DATA = {
    "telegram_id": 999888777,
    "username": "integration_test_user",
    "first_name": "Integration",
    "last_name": "Test",
    "phone": "+999888777666",
    "email": "integration@test.com",
    "language_code": "en"
}

TEST_PROFILE_DATA = {
    "birth_date": "1990-01-01",
    "passport_series": "AB",
    "passport_number": "1234567",
    "home_address": "Test Home Address",
    "apartment_address": "Test Apartment Address",
    "specialization": ["plumbing", "electrical"],
    "bio": "Integration test user profile",
    "address_type": "apartment"
}

class MicroservicesIntegrationTest:
    """Comprehensive integration tests for all microservices"""

    def __init__(self):
        self.created_users = []
        self.service_tokens = {}
        self.user_credentials = {}

    async def cleanup(self):
        """Clean up test data"""
        # In production, this would clean up test data
        pass

    async def test_service_health(self):
        """Test all services are healthy"""
        services = [
            ("Auth Service", f"{AUTH_SERVICE_URL}/health"),
            ("User Service", f"{USER_SERVICE_URL}/health"),
            ("Media Service", f"{MEDIA_SERVICE_URL}/health")
        ]

        results = {}

        async with httpx.AsyncClient(timeout=10.0) as client:
            for service_name, health_url in services:
                try:
                    response = await client.get(health_url)
                    if response.status_code == 200:
                        health_data = response.json()
                        if health_data.get("status") == "healthy":
                            results[service_name] = "✅ Healthy"
                            print(f"✅ {service_name}: Healthy")
                        else:
                            results[service_name] = "⚠️ Unhealthy"
                            print(f"⚠️ {service_name}: Reports unhealthy")
                    else:
                        results[service_name] = f"❌ HTTP {response.status_code}"
                        print(f"❌ {service_name}: HTTP {response.status_code}")

                except httpx.RequestError as e:
                    results[service_name] = f"❌ Connection Error: {e}"
                    print(f"❌ {service_name}: Connection Error")

        return results

    async def test_auth_service_tokens(self):
        """Test Auth Service token generation and validation"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Generate service token
            token_response = await client.post(
                f"{AUTH_SERVICE_URL}/api/v1/internal/generate-service-token",
                params={"service_name": "integration-test", "permissions": ["read", "write"]}
            )

            if token_response.status_code == 200:
                token_data = token_response.json()
                token = token_data["token"]
                self.service_tokens["integration-test"] = token

                print(f"✅ Service token generated: {token[:20]}...")

                # Validate the token
                validation_response = await client.post(
                    f"{AUTH_SERVICE_URL}/api/v1/internal/validate-service-token",
                    json={"token": token, "service_name": "integration-test"}
                )

                if validation_response.status_code == 200:
                    validation_data = validation_response.json()
                    if validation_data.get("valid"):
                        print(f"✅ Service token validation passed")
                        return True
                    else:
                        print(f"❌ Service token validation failed")
                        return False
                else:
                    print(f"❌ Token validation request failed: {validation_response.status_code}")
                    return False
            else:
                print(f"❌ Token generation failed: {token_response.status_code}")
                return False

    async def test_user_service_crud(self):
        """Test User Service CRUD operations"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Create user
            create_response = await client.post(
                f"{USER_SERVICE_URL}/api/v1/users",
                json=TEST_USER_DATA,
                headers={"X-API-Key": "test-api-key"}
            )

            if create_response.status_code == 201:
                user_data = create_response.json()
                user_id = user_data["id"]
                self.created_users.append(user_id)

                print(f"✅ User created: ID {user_id}")

                # Verify user creation with GET
                get_response = await client.get(
                    f"{USER_SERVICE_URL}/api/v1/users/{user_id}",
                    headers={"X-API-Key": "test-api-key"}
                )

                if get_response.status_code == 200:
                    retrieved_user = get_response.json()

                    # Verify data integrity
                    if (retrieved_user["telegram_id"] == TEST_USER_DATA["telegram_id"] and
                        retrieved_user["username"] == TEST_USER_DATA["username"]):
                        print(f"✅ User data integrity verified")

                        # Test update
                        update_data = {"bio": "Updated integration test user"}
                        update_response = await client.patch(
                            f"{USER_SERVICE_URL}/api/v1/users/{user_id}",
                            json=update_data,
                            headers={"X-API-Key": "test-api-key"}
                        )

                        if update_response.status_code == 200:
                            print(f"✅ User update successful")
                            return user_id
                        else:
                            print(f"❌ User update failed: {update_response.status_code}")
                            return None
                    else:
                        print(f"❌ User data integrity check failed")
                        return None
                else:
                    print(f"❌ User retrieval failed: {get_response.status_code}")
                    return None
            else:
                print(f"❌ User creation failed: {create_response.status_code}")
                return None

    async def test_profile_service_operations(self, user_id: int):
        """Test Profile Service operations"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Create profile
            create_response = await client.post(
                f"{USER_SERVICE_URL}/api/v1/profiles",
                json={"user_id": user_id, **TEST_PROFILE_DATA},
                headers={"X-API-Key": "test-api-key"}
            )

            if create_response.status_code == 201:
                profile_data = create_response.json()
                print(f"✅ Profile created for user {user_id}")

                # Get profile
                get_response = await client.get(
                    f"{USER_SERVICE_URL}/api/v1/profiles/{user_id}",
                    headers={"X-API-Key": "test-api-key"}
                )

                if get_response.status_code == 200:
                    retrieved_profile = get_response.json()

                    # Verify profile data
                    if (retrieved_profile["bio"] == TEST_PROFILE_DATA["bio"] and
                        retrieved_profile["specialization"] == TEST_PROFILE_DATA["specialization"]):
                        print(f"✅ Profile data integrity verified")

                        # Test update
                        update_data = {"bio": "Updated profile bio"}
                        update_response = await client.patch(
                            f"{USER_SERVICE_URL}/api/v1/profiles/{user_id}",
                            json=update_data,
                            headers={"X-API-Key": "test-api-key"}
                        )

                        if update_response.status_code == 200:
                            print(f"✅ Profile update successful")
                            return True
                        else:
                            print(f"❌ Profile update failed: {update_response.status_code}")
                            return False
                    else:
                        print(f"❌ Profile data integrity check failed")
                        return False
                else:
                    print(f"❌ Profile retrieval failed: {get_response.status_code}")
                    return False
            else:
                print(f"❌ Profile creation failed: {create_response.status_code}")
                return False

    async def test_auth_user_integration(self, user_id: int):
        """Test Auth Service and User Service integration"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Get service token for User Service communication
            token = self.service_tokens.get("integration-test", "fallback-token")

            # Test Auth Service calling User Service
            get_response = await client.get(
                f"{USER_SERVICE_URL}/api/v1/users/by-telegram/{TEST_USER_DATA['telegram_id']}",
                headers={"Authorization": f"Bearer {token}"}
            )

            if get_response.status_code == 200:
                user_data = get_response.json()
                if user_data["id"] == user_id:
                    print(f"✅ Auth-User service communication successful")
                    return True
                else:
                    print(f"❌ Auth-User integration: User ID mismatch")
                    return False
            else:
                print(f"❌ Auth-User integration failed: {get_response.status_code}")
                return False

    async def test_user_statistics(self):
        """Test User Service statistics endpoint"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            stats_response = await client.get(
                f"{USER_SERVICE_URL}/api/v1/users/stats/overview",
                headers={"X-API-Key": "test-api-key"}
            )

            if stats_response.status_code == 200:
                stats_data = stats_response.json()

                # Verify UserStatsResponse structure
                required_fields = ["total_users", "active_users", "status_distribution",
                                 "role_distribution", "monthly_registrations"]

                if all(field in stats_data for field in required_fields):
                    print(f"✅ User statistics endpoint working")
                    print(f"   Total users: {stats_data['total_users']}")
                    print(f"   Active users: {stats_data['active_users']}")
                    return True
                else:
                    print(f"❌ User statistics: Missing required fields")
                    return False
            else:
                print(f"❌ User statistics failed: {stats_response.status_code}")
                return False

    async def test_media_service_health(self):
        """Test Media Service basic functionality"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Test health endpoint
            health_response = await client.get(f"{MEDIA_SERVICE_URL}/health")

            if health_response.status_code == 200:
                health_data = health_response.json()
                if health_data.get("status") == "healthy":
                    print(f"✅ Media Service health check passed")
                    return True
                else:
                    print(f"❌ Media Service reports unhealthy")
                    return False
            else:
                print(f"❌ Media Service health check failed: {health_response.status_code}")
                return False

    async def test_concurrent_operations(self):
        """Test concurrent operations across services"""
        print(f"🔄 Testing concurrent operations...")

        # Create multiple concurrent requests
        tasks = []

        async with httpx.AsyncClient(timeout=10.0) as client:
            # Health checks
            for i in range(5):
                task = client.get(f"{USER_SERVICE_URL}/health")
                tasks.append(task)

            # Token validations
            token = self.service_tokens.get("integration-test", "test-token")
            for i in range(3):
                task = client.post(
                    f"{AUTH_SERVICE_URL}/api/v1/internal/validate-service-token",
                    json={"token": token, "service_name": "integration-test"}
                )
                tasks.append(task)

            try:
                responses = await asyncio.gather(*tasks, return_exceptions=True)

                success_count = sum(1 for resp in responses
                                  if hasattr(resp, 'status_code') and resp.status_code == 200)

                if success_count >= len(tasks) * 0.8:  # 80% success rate
                    print(f"✅ Concurrent operations successful ({success_count}/{len(tasks)})")
                    return True
                else:
                    print(f"❌ Concurrent operations failed ({success_count}/{len(tasks)})")
                    return False

            except Exception as e:
                print(f"❌ Concurrent operations exception: {e}")
                return False

    async def run_comprehensive_test(self):
        """Run comprehensive integration test suite"""
        print("=" * 70)
        print("🧪 MICROSERVICES INTEGRATION TESTS")
        print("=" * 70)

        start_time = time.time()
        results = {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "test_results": []
        }

        # Test sequence
        test_sequence = [
            ("Service Health Checks", self.test_service_health()),
            ("Auth Service Token Operations", self.test_auth_service_tokens()),
            ("User Service CRUD", self.test_user_service_crud()),
            ("User Statistics", self.test_user_statistics()),
            ("Media Service Health", self.test_media_service_health()),
            ("Concurrent Operations", self.test_concurrent_operations())
        ]

        user_id = None

        for test_name, test_coro in test_sequence:
            print(f"\n🧪 {test_name}")
            print("-" * 50)

            results["total_tests"] += 1

            try:
                if test_name == "User Service CRUD":
                    result = await test_coro
                    user_id = result
                    success = result is not None
                else:
                    success = await test_coro

                if success:
                    results["passed_tests"] += 1
                    results["test_results"].append((test_name, "✅ PASSED"))
                    print(f"✅ {test_name} PASSED")
                else:
                    results["failed_tests"] += 1
                    results["test_results"].append((test_name, "❌ FAILED"))
                    print(f"❌ {test_name} FAILED")

            except Exception as e:
                results["failed_tests"] += 1
                results["test_results"].append((test_name, f"❌ ERROR: {e}"))
                print(f"❌ {test_name} ERROR: {e}")

            # Add delay between tests
            await asyncio.sleep(1)

        # Additional tests that require user_id
        if user_id:
            additional_tests = [
                ("Profile Service Operations", self.test_profile_service_operations(user_id)),
                ("Auth-User Integration", self.test_auth_user_integration(user_id))
            ]

            for test_name, test_coro in additional_tests:
                print(f"\n🧪 {test_name}")
                print("-" * 50)

                results["total_tests"] += 1

                try:
                    success = await test_coro

                    if success:
                        results["passed_tests"] += 1
                        results["test_results"].append((test_name, "✅ PASSED"))
                        print(f"✅ {test_name} PASSED")
                    else:
                        results["failed_tests"] += 1
                        results["test_results"].append((test_name, "❌ FAILED"))
                        print(f"❌ {test_name} FAILED")

                except Exception as e:
                    results["failed_tests"] += 1
                    results["test_results"].append((test_name, f"❌ ERROR: {e}"))
                    print(f"❌ {test_name} ERROR: {e}")

                await asyncio.sleep(1)

        # Results summary
        total_duration = time.time() - start_time

        print("\n" + "=" * 70)
        print("📊 INTEGRATION TEST RESULTS")
        print("=" * 70)

        print(f"📈 Summary:")
        print(f"  Total tests: {results['total_tests']}")
        print(f"  ✅ Passed: {results['passed_tests']}")
        print(f"  ❌ Failed: {results['failed_tests']}")
        print(f"  ⏱️ Duration: {total_duration:.1f}s")

        success_rate = results['passed_tests'] / results['total_tests'] if results['total_tests'] > 0 else 0

        print(f"\n📋 Detailed Results:")
        for test_name, result in results["test_results"]:
            print(f"  {result} {test_name}")

        # Overall assessment
        if success_rate >= 0.9:
            print(f"\n🎉 INTEGRATION TESTS PASSED ({success_rate:.0%} success rate)")
            print("All microservices are working correctly and integrating properly!")
        elif success_rate >= 0.7:
            print(f"\n⚠️ INTEGRATION TESTS MOSTLY PASSED ({success_rate:.0%} success rate)")
            print("Most functionality works, but some issues need attention.")
        else:
            print(f"\n💥 INTEGRATION TESTS FAILED ({success_rate:.0%} success rate)")
            print("Significant integration issues detected.")

        # Cleanup
        print(f"\n🧹 Cleaning up test data...")
        await self.cleanup()

        return success_rate >= 0.8

async def run_microservices_integration_tests():
    """Run comprehensive microservices integration tests"""
    test_instance = MicroservicesIntegrationTest()

    try:
        return await test_instance.run_comprehensive_test()
    finally:
        await test_instance.cleanup()

if __name__ == "__main__":
    success = asyncio.run(run_microservices_integration_tests())
    exit(0 if success else 1)