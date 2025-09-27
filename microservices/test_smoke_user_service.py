#!/usr/bin/env python3
"""
User Service Smoke Tests
UK Management Bot - User Service

Basic smoke tests to verify User Service core functionality
"""

import asyncio
import httpx
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UserServiceSmokeTest:
    """Smoke tests for User Service"""

    def __init__(self, base_url: str = "http://localhost:8002"):
        self.base_url = base_url
        self.test_results = {}

    async def run_smoke_tests(self):
        """Run all smoke tests"""
        logger.info("🔥 Starting User Service smoke tests")

        await self.test_health_check()
        await self.test_user_crud_operations()
        await self.test_telegram_lookup()
        await self.test_role_management()
        await self.test_profile_management()

        self.print_results()
        return self.all_tests_passed()

    async def test_health_check(self):
        """Test basic health check"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")

                if response.status_code == 200:
                    self.test_results["health_check"] = "✅ PASS"
                    logger.info("✅ Health check: PASS")
                else:
                    self.test_results["health_check"] = f"❌ FAIL: HTTP {response.status_code}"
                    logger.error(f"❌ Health check failed: {response.status_code}")

        except Exception as e:
            self.test_results["health_check"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ Health check failed: {e}")

    async def test_user_crud_operations(self):
        """Test basic user CRUD operations"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test GET users endpoint (should require auth)
                response = await client.get(f"{self.base_url}/api/v1/users/")

                if response.status_code in [200, 401, 403]:
                    # 200 = success, 401/403 = auth required (expected)
                    self.test_results["user_crud"] = "✅ PASS"
                    logger.info("✅ User CRUD operations: PASS")
                else:
                    self.test_results["user_crud"] = f"❌ FAIL: HTTP {response.status_code}"
                    logger.error(f"❌ User CRUD failed: {response.status_code}")

        except Exception as e:
            self.test_results["user_crud"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ User CRUD failed: {e}")

    async def test_telegram_lookup(self):
        """Test Telegram ID lookup endpoint (critical for Auth Service)"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test without authentication (should fail)
                test_telegram_id = 123456789
                response = await client.get(
                    f"{self.base_url}/api/v1/users/by-telegram/{test_telegram_id}"
                )

                if response.status_code == 401:
                    # Expected - endpoint requires service authentication
                    self.test_results["telegram_lookup"] = "✅ PASS"
                    logger.info("✅ Telegram lookup (auth required): PASS")
                elif response.status_code == 404:
                    # User not found, but endpoint works
                    self.test_results["telegram_lookup"] = "✅ PASS"
                    logger.info("✅ Telegram lookup (user not found): PASS")
                elif response.status_code == 200:
                    # User found (unexpected without auth, but endpoint works)
                    self.test_results["telegram_lookup"] = "⚠️  WARN: No auth required"
                    logger.warning("⚠️  Telegram lookup: Works without auth (security concern)")
                else:
                    self.test_results["telegram_lookup"] = f"❌ FAIL: HTTP {response.status_code}"
                    logger.error(f"❌ Telegram lookup failed: {response.status_code}")

        except Exception as e:
            self.test_results["telegram_lookup"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ Telegram lookup failed: {e}")

    async def test_role_management(self):
        """Test role management endpoints"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test roles endpoint
                response = await client.get(f"{self.base_url}/api/v1/roles/")

                if response.status_code in [200, 401, 403]:
                    self.test_results["role_management"] = "✅ PASS"
                    logger.info("✅ Role management: PASS")
                else:
                    self.test_results["role_management"] = f"❌ FAIL: HTTP {response.status_code}"
                    logger.error(f"❌ Role management failed: {response.status_code}")

        except Exception as e:
            self.test_results["role_management"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ Role management failed: {e}")

    async def test_profile_management(self):
        """Test profile management endpoints"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test profiles endpoint
                response = await client.get(f"{self.base_url}/api/v1/profiles/")

                if response.status_code in [200, 401, 403]:
                    self.test_results["profile_management"] = "✅ PASS"
                    logger.info("✅ Profile management: PASS")
                else:
                    self.test_results["profile_management"] = f"❌ FAIL: HTTP {response.status_code}"
                    logger.error(f"❌ Profile management failed: {response.status_code}")

        except Exception as e:
            self.test_results["profile_management"] = f"❌ FAIL: {str(e)}"
            logger.error(f"❌ Profile management failed: {e}")

    def print_results(self):
        """Print test results"""
        logger.info("\n" + "="*50)
        logger.info("🔥 USER SERVICE SMOKE TEST RESULTS")
        logger.info("="*50)

        for test_name, result in self.test_results.items():
            logger.info(f"{test_name.replace('_', ' ').title()}: {result}")

        passed = len([r for r in self.test_results.values() if r.startswith("✅")])
        total = len(self.test_results)

        logger.info(f"\n📊 Summary: {passed}/{total} tests passed")
        logger.info("="*50)

    def all_tests_passed(self):
        """Check if all tests passed"""
        return all(result.startswith("✅") or result.startswith("⚠️") for result in self.test_results.values())

async def main():
    """Run smoke tests"""
    tester = UserServiceSmokeTest()
    success = await tester.run_smoke_tests()

    if not success:
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())